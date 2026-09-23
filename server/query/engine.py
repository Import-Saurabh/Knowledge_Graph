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