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


def format_compact_triples(subgraph: dict, entities: list[dict]) -> tuple[str, str]:
    """Serialize graph topology into concise linearized notation and deduplicate entity attributes."""
    entity_dict = {}
    for e in entities:
        eid = e.get("id")
        if eid:
            name = e.get("canonical_name") or e.get("label") or eid
            etype = e.get("entity_type") or e.get("type") or "concept"
            desc = (e.get("description") or "").strip()
            entity_dict[eid] = {"name": name, "type": etype, "desc": desc}

    # Format compact linearized relationships: [Subject] -[:REL_TYPE]-> [Object] | context
    rel_lines = []
    seen_edges = set()
    for l in subgraph.get("links", [])[:35]:
        s = l["source"]["id"] if isinstance(l.get("source"), dict) else l.get("source", "")
        t = l["target"]["id"] if isinstance(l.get("target"), dict) else l.get("target", "")
        rtype = l.get("type", "RELATED_TO").upper()
        rdesc = (l.get("description") or "").strip()

        if not s or not t or (s, t, rtype) in seen_edges:
            continue
        seen_edges.add((s, t, rtype))

        s_name = entity_dict.get(s, {}).get("name", s)
        t_name = entity_dict.get(t, {}).get("name", t)

        if rdesc:
            rel_lines.append(f"[{s_name}] -[:{rtype}]-> [{t_name}] | {rdesc}")
        else:
            rel_lines.append(f"[{s_name}] -[:{rtype}]-> [{t_name}]")

    # Format deduplicated entity attributes
    ent_lines = []
    seen_eids = set()
    for e in entities[:20]:
        eid = e.get("id")
        if not eid or eid in seen_eids:
            continue
        seen_eids.add(eid)
        name = e.get("canonical_name") or e.get("label") or eid
        etype = e.get("entity_type") or e.get("type") or "concept"
        desc = (e.get("description") or "").strip()

        if desc:
            ent_lines.append(f"- [{eid}] {name} ({etype}): {desc}")
        else:
            ent_lines.append(f"- [{eid}] {name} ({etype})")

    ent_text = "\n".join(ent_lines) if ent_lines else "No specific entities found."
    rel_text = "\n".join(rel_lines) if rel_lines else "No direct relationships found."
    return ent_text, rel_text


def format_deduplicated_sources(articles: list[dict], claims: list[dict]) -> tuple[str, str]:
    """Eliminate redundant article text chunks when factual claims already capture the answer."""
    claim_lines = []
    claimed_article_ids = set()

    for c in claims[:12]:
        attrib = c.get("attribution", "media")
        text = (c.get("claim_text") or "").strip()
        headline = c.get("headline", "Report")
        art_id = c.get("source_article_id")
        if art_id:
            claimed_article_ids.add(art_id)
        if text:
            claim_lines.append(f"- ({attrib}) \"{text}\" [Source: {headline}]")

    art_lines = []
    for a in articles[:8]:
        pub = a.get("publisher", "Publisher")
        hl = a.get("headline", "Untitled")
        date = a.get("published_at", "Recent")
        url = a.get("url", "")
        aid = a.get("id")

        if aid in claimed_article_ids:
            art_lines.append(f"- [{pub}] \"{hl}\" ({date}) <{url}> [Captured in claims]")
        else:
            summary = (a.get("summary") or "").strip()
            if summary:
                art_lines.append(f"- [{pub}] \"{hl}\" ({date}) <{url}>\n  Key excerpt: {summary[:160]}")
            else:
                art_lines.append(f"- [{pub}] \"{hl}\" ({date}) <{url}>")

    claims_text = "\n".join(claim_lines) if claim_lines else "No specific claims recorded."
    arts_text = "\n".join(art_lines) if art_lines else "No direct articles retrieved."
    return claims_text, arts_text


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
        """Synthesize a graph-grounded response with compact serialization and KV caching."""
        # 1. Format compact graph context & deduplicate sources
        ent_text, rel_text = format_compact_triples(subgraph, entities)
        claims_text, arts_text = format_deduplicated_sources(articles, claims)

        event_lines = [
            f"- Event [{ev.get('id')}]: {ev.get('summary')} (Time: {ev.get('event_time', 'recent')}, Loc: {ev.get('location', 'N/A')})"
            for ev in events[:8]
        ]
        events_text = "\n".join(event_lines) if event_lines else "No specific events recorded."

        context_text = f"""### KNOWLEDGE GRAPH TOPOLOGY (LINEARIZED TRIPLES):
{rel_text}

### ENTITY ATTRIBUTES:
{ent_text}

### RECORDED EVENTS:
{events_text}

### EVIDENCE CLAIMS:
{claims_text}

### SUPPORTING SOURCES:
{arts_text}
"""

        messages = []
        if conversation_history:
            for prev in conversation_history[-4:]:  # last 2 turns
                messages.append({
                    "role": prev["role"],
                    "content": prev["content"],
                })

        user_content = (
            f"### EVIDENCE CONTEXT\n{context_text}\n\n"
            f"### DIRECTIVE & QUESTION\nUser Question: {question}\n\n"
            f"Please synthesize a comprehensive, evidence-grounded briefing based strictly on the knowledge graph context above."
        )
        messages.append({"role": "user", "content": user_content})

        # 2. KV Prompt Caching: use cache_control ephemeral block with string fallback
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1536,
                system=[
                    {
                        "type": "text",
                        "text": SYNTHESIS_SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=messages,
            )
            raw_answer = response.content[0].text.strip()
        except Exception:
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
