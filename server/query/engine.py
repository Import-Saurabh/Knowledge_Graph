"""Master query engine coordinating graph retrieval, fresh research, and answer synthesis."""
from __future__ import annotations

import uuid
from typing import Any

from server.database import GraphStore, get_db
from server.models import Message, QueryRequest, QueryResponse, utc_now_iso
from server.query.researcher import QueryResearcher
from server.query.retriever import GraphRetriever
from server.query.synthesizer import AnswerSynthesizer


class QueryEngine:
    """Coordinates end-to-end question answering grounded in graph context and fresh news research."""

    def __init__(self):
        self.retriever = GraphRetriever()
        self.researcher = QueryResearcher()
        self.synthesizer = AnswerSynthesizer()

    def answer_question(self, req: QueryRequest) -> QueryResponse:
        question = req.question.strip()
        conv_id = req.conversation_id or str(uuid.uuid4())

        # Ensure conversation exists
        conv = GraphStore.get_conversation(conv_id)
        if not conv:
            GraphStore.create_conversation(conv_id, title=question[:50])
            conv_history = []
        else:
            conv_history = conv.get("messages", [])

        # 1. Save user message
        user_msg_id = str(uuid.uuid4())
        user_msg = Message(
            id=user_msg_id,
            conversation_id=conv_id,
            role="user",
            content=question,
            created_at=utc_now_iso(),
        )
        GraphStore.save_message(user_msg)

        # 2. Identify candidate entities from question
        entities = self.retriever.identify_entities_in_text(question)

        # 3. Assess if fresh news research is required
        should_research, reason = self.researcher.should_trigger_research(
            question, entities, force=req.force_research
        )

        research_meta: dict[str, Any] = {"research_triggered": False, "reason": reason}
        if should_research:
            print(f"[QueryEngine] Triggering fresh research. Reason: {reason}")
            research_meta = self.researcher.perform_research(question, entities)
            # Re-fetch entities after new graph writes
            entities = self.retriever.identify_entities_in_text(question)

        # 4. If still no entities identified, get top entities by connectivity from DB
        if not entities:
            with get_db() as conn:
                rows = conn.execute("""
                    SELECT e.* FROM entities e
                    LEFT JOIN (
                        SELECT entity_id, COUNT(*) as deg FROM (
                            SELECT source_id as entity_id FROM relationships
                            UNION ALL
                            SELECT target_id as entity_id FROM relationships
                        ) GROUP BY entity_id
                    ) d ON e.id = d.entity_id
                    ORDER BY COALESCE(d.deg, 0) DESC
                    LIMIT 10
                """).fetchall()
                entities = [dict(r) for r in rows]

        entity_ids = [e["id"] for e in entities]

        # 5. Retrieve graph context: subgraphs, events, claims, and articles
        subgraph = self.retriever.get_multi_hop_context(entity_ids, max_hops=2)
        events = self.retriever.get_events_for_entities(entity_ids, limit=8)
        claims = self.retriever.get_claims_and_evidence(entity_ids, limit=12)
        articles = self.retriever.get_recent_articles_for_entities(entity_ids, limit=8)
        if research_meta.get("articles"):
            existing_urls = {a.get("url") for a in articles}
            for ra in research_meta["articles"]:
                if ra.get("url") not in existing_urls:
                    articles.append(ra)
                    existing_urls.add(ra.get("url"))

        # 6. Synthesize evidence-backed response
        answer, citations, ref_entity_ids, ref_event_ids = self.synthesizer.synthesize(
            question=question,
            entities=entities,
            subgraph=subgraph,
            events=events,
            claims=claims,
            articles=articles,
            conversation_history=conv_history,
        )

        # 7. Save assistant message
        asst_msg_id = str(uuid.uuid4())
        asst_msg = Message(
            id=asst_msg_id,
            conversation_id=conv_id,
            role="assistant",
            content=answer,
            citations=[c.model_dump() for c in citations],
            entity_ids=ref_entity_ids,
            event_ids=ref_event_ids,
            research_metadata=research_meta,
            created_at=utc_now_iso(),
        )
        GraphStore.save_message(asst_msg)

        return QueryResponse(
            answer=answer,
            citations=citations,
            entity_ids=ref_entity_ids,
            event_ids=ref_event_ids,
            research_metadata=research_meta,
            conversation_id=conv_id,
            message_id=asst_msg_id,
        )
