"""LLM-based answer synthesizer grounded in knowledge graph topology and evidence citations."""
from __future__ import annotations

import json
import re
from typing import Any

from anthropic import Anthropic

from server.config import settings
from server.models import Citation

SYNTHESIS_SYSTEM_PROMPT = """You are the DriftForge Intelligence Analyst, an AI that synthesizes comprehensive, factual briefings grounded strictly in an evidence-backed Knowledge Graph and real news sources.

Instructions:
1. Provide a well-structured, objective, and analytical briefing responding directly to the user's question.
2. Structure your briefing logically with markdown headers (e.g., ## Key Developments, ## Actor Analysis, ## Strategic Implications).
3. Ground your facts strictly in the provided GRAPH TOPOLOGY, EVENTS, and SOURCE ARTICLES.
4. Distinguish clearly between independently verified events, official government claims, and media reports.
5. In your text, cite sources inline where appropriate, e.g. [BBC News](url) or (Source: Al Jazeera).
6. At the very end of your response, output a JSON block wrapped in ```explore_graph ... ``` containing the entity IDs and event IDs directly relevant to your answer, so the user can explore them in the 3D graph view:
```explore_graph
{
  "entity_ids": ["entity-id-1", "entity-id-2"],
  "event_ids": ["event-id-1"]
}
```
"""


class AnswerSynthesizer:
    """Generates source-backed intelligence briefings using LLM."""

    def __init__(self):
        client_kwargs = {}
        if settings.anthropic_base_url:
            client_kwargs["base_url"] = settings.anthropic_base_url
        if settings.anthropic_api_key:
            client_kwargs["api_key"] = settings.anthropic_api_key
        client_kwargs["timeout"] = settings.llm_timeout

        self.client = Anthropic(**client_kwargs)
        self.model = settings.llm_model

    def synthesize(
        self,
        question: str,
        entities: list[dict],
        subgraph: dict,
        events: list[dict],
        claims: list[dict],
        articles: list[dict],
        conversation_history: list[dict] = None,
    ) -> tuple[str, list[Citation], list[str], list[str]]:
        """Synthesize a graph-grounded response."""
        # 1. Format graph context
        ent_lines = []
        for e in entities[:20]:
            name = e.get('canonical_name') or e.get('label') or e.get('id', 'Unknown')
            etype = e.get('entity_type') or e.get('type') or 'concept'
            eid = e.get('id', 'unknown')
            desc = e.get('description', '')
            ent_lines.append(f"- {name} (Type: {etype}, ID: {eid}): {desc}")

        rel_lines = []
        for l in subgraph.get("links", [])[:30]:
            s = l['source']['id'] if isinstance(l.get('source'), dict) else l.get('source', '')
            t = l['target']['id'] if isinstance(l.get('target'), dict) else l.get('target', '')
            rtype = l.get('type', 'RELATED_TO')
            rdesc = l.get('description', '')
            rel_lines.append(f"- [{s}] --({rtype})--> [{t}]: {rdesc}")
        event_lines = [
            f"- Event [{ev.get('id')}]: {ev.get('summary')} (Time: {ev.get('event_time', 'recent')}, Loc: {ev.get('location', 'N/A')})"
            for ev in events[:8]
        ]
        claim_lines = [
            f"- Claim ({c.get('attribution', 'media')}): \"{c.get('claim_text')}\" [Source: {c.get('headline', 'Article')}]"
            for c in claims[:12]
        ]
        art_lines = [
            f"- [{a.get('publisher', 'Publisher')}] \"{a.get('headline')}\" ({a.get('published_at', 'Recent')})\n  URL: {a.get('url')}\n  Excerpt: {a.get('summary', '')[:250]}"
            for a in articles[:8]
        ]

        context_text = f"""### KNOWLEDGE GRAPH ENTITIES:
{chr(10).join(ent_lines) or 'No specific entities found.'}

### GRAPH RELATIONSHIPS:
{chr(10).join(rel_lines) or 'No direct relationships found.'}

### RECORDED EVENTS:
{chr(10).join(event_lines) or 'No specific events recorded.'}

### EVIDENCE CLAIMS:
{chr(10).join(claim_lines) or 'No specific claims recorded.'}

### SUPPORTING ARTICLES & SOURCES:
{chr(10).join(art_lines) or 'No direct articles retrieved.'}
"""

        messages = []
        if conversation_history:
            for prev in conversation_history[-4:]:  # last 2 turns
                messages.append({
                    "role": prev["role"],
                    "content": prev["content"],
                })

        user_content = (
            f"User Question: {question}\n\n"
            f"Evidence & Knowledge Graph Context:\n{context_text}\n\n"
            f"Please synthesize a comprehensive, evidence-grounded briefing."
        )
        messages.append({"role": "user", "content": user_content})

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1536,
                system=SYNTHESIS_SYSTEM_PROMPT,
                messages=messages,
            )
            raw_answer = response.content[0].text.strip()
        except Exception as e:
            raw_answer = f"Error during briefing synthesis: {e}"

        # Extract explore_graph block
        entity_ids = [e["id"] for e in entities]
        event_ids = [ev["id"] for ev in events]

        graph_match = re.search(r"```explore_graph\s*({.*?})\s*```", raw_answer, re.DOTALL)
        if graph_match:
            try:
                gdata = json.loads(graph_match.group(1))
                extracted_ents = gdata.get("entity_ids", [])
                if extracted_ents:
                    entity_ids = extracted_ents
                extracted_evs = gdata.get("event_ids", [])
                if extracted_evs:
                    event_ids = extracted_evs
            except Exception:
                pass
            # Clean explore_graph from user-visible answer
            clean_answer = re.sub(r"```explore_graph\s*({.*?})\s*```", "", raw_answer, flags=re.DOTALL).strip()
        else:
            clean_answer = raw_answer

        # Construct citations list
        citations = []
        seen_urls = set()
        for art in articles:
            u = art.get("url", "")
            if u and u not in seen_urls:
                seen_urls.add(u)
                citations.append(Citation(
                    id=art.get("id", str(len(citations))),
                    headline=art.get("headline"),
                    publisher=art.get("publisher"),
                    url=u,
                    published_at=art.get("published_at"),
                    summary=art.get("summary"),
                ))

        return clean_answer, citations, entity_ids, event_ids
