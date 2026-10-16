"""LLM-based entity, event, relationship, and evidence extraction."""
from __future__ import annotations

import json
import re
import sys
from typing import Any

from anthropic import Anthropic

from server.config import settings
from server.models import Article

EXTRACTION_SYSTEM_PROMPT = """You are an expert geopolitical intelligence analyst building a knowledge graph from current news reporting.

Given the news articles below, extract:
1. High-influence entities (persons, organisations, countries, locations, armed groups, concepts).
2. Concrete events (strikes, summits, declarations, sanctions, agreements, incidents).
3. Directed relationships linking entities to entities or events.
4. Specific claims/evidence statements with source attribution.

Entity types (use exactly):
  person | organisation | country | location | government | armed_group | concept

Event types (use exactly):
  military_action | diplomatic_meeting | agreement | statement | sanctions | incident | economic_action | legal_action

Relationship types (use exactly):
  causes | caused_by | involves | opposes | supports | allies_with | threatens | located_in | responds_to | impacts | negotiates_with | accuses | sanctions | participated_in

Rules:
- Entity and event IDs must be lowercase and hyphen-separated (e.g. "saudi-arabia", "houthi-movement", "2026-10-strike-al-jawf").
- For events, provide an estimated or stated event_time (ISO date YYYY-MM-DD if known) and location.
- For claims, quote or closely summarize the assertion and note who made it (attribution).
- Every relationship source and target MUST match an entity or event ID declared in your lists.
- Link each item to the relevant article number (e.g. article_index: 1).
- Aim for 10-25 high-influence entities, 2-6 events, and 15-35 relationships.

Respond with ONLY valid JSON in this exact structure:
{
  "entities": [
    {
      "id": "slug-id",
      "label": "Human Readable Label",
      "type": "country",
      "description": "Contextual description from articles",
      "aliases": ["Alternative Name"]
    }
  ],
  "events": [
    {
      "id": "slug-id",
      "event_type": "military_action",
      "summary": "Concise summary of what occurred",
      "event_time": "2026-10-11",
      "location": "Red Sea",
      "participants": ["entity-id-1", "entity-id-2"],
      "article_index": 1
    }
  ],
  "relationships": [
    {
      "source": "entity-id-1",
      "target": "entity-id-2",
      "type": "opposes",
      "description": "Description of how they relate",
      "article_index": 1
    }
  ],
  "claims": [
    {
      "claim_text": "Assertion text",
      "subject": "entity-id-1",
      "predicate": "launched drone towards",
      "object": "entity-id-2",
      "attribution": "Ministry of Defense spokesman",
      "article_index": 1
    }
  ]
}"""


class LLMExtractor:
    """Extracts structured graph entities, events, relationships, and claims using LLM."""

    def __init__(self):
        client_kwargs = {}
        if settings.anthropic_base_url:
            client_kwargs["base_url"] = settings.anthropic_base_url
        if settings.anthropic_api_key:
            client_kwargs["api_key"] = settings.anthropic_api_key
        client_kwargs["timeout"] = settings.llm_timeout

        self.client = Anthropic(**client_kwargs)
        self.model = settings.llm_model

    def _extract_chunk(self, chunk_articles: list[Article], offset: int = 0) -> dict[str, Any]:
        """Extract graph elements from a single chunk of articles with index offset adjustment."""
        if not chunk_articles:
            return {"entities": [], "events": [], "relationships": [], "claims": []}

        articles_text = "\n\n".join(
            f"ARTICLE {i + 1} ({a.publisher or 'Unknown Source'} - {a.published_at or 'Today'}):\n"
            f"Title: {a.headline}\n"
            f"Content: {a.content_excerpt or a.summary or ''}\n"
            f"URL: {a.url}"
            for i, a in enumerate(chunk_articles)
        )

        prompt = (
            f"Extract the news knowledge graph, events, relationships, and claims from these {len(chunk_articles)} articles:\n\n"
            f"{articles_text}"
        )

        for attempt in range(2):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=8192,
                    system=EXTRACTION_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw_text = response.content[0].text.strip()
                json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
                if json_match:
                    raw_text = json_match.group(1).strip()
                else:
                    brace_match = re.search(r"(\{.*\})", raw_text, re.DOTALL)
                    if brace_match:
                        raw_text = brace_match.group(1).strip()

                data = json.loads(raw_text)

                events = data.get("events", [])
                relationships = data.get("relationships", [])
                claims = data.get("claims", [])

                # Re-map 1-based article_index to match global article list
                if offset > 0:
                    for ev in events:
                        if "article_index" in ev:
                            ev["article_index"] = ev["article_index"] + offset
                    for rel in relationships:
                        if "article_index" in rel:
                            rel["article_index"] = rel["article_index"] + offset
                    for cl in claims:
                        if "article_index" in cl:
                            cl["article_index"] = cl["article_index"] + offset

                return {
                    "entities": data.get("entities", []),
                    "events": events,
                    "relationships": relationships,
                    "claims": claims,
                }
            except Exception as e:
                err_str = str(e)
                if "429" in err_str and attempt == 0:
                    import time
                    time.sleep(2.0)
                    continue
                print(f"[LLMExtractor] Error during chunk extraction (offset {offset}): {e}", file=sys.stderr)
                return {"entities": [], "events": [], "relationships": [], "claims": []}

    def extract(self, articles: list[Article]) -> dict[str, Any]:
        """Perform structured extraction on articles, using parallel chunking for low latency."""
        if not articles:
            return {"entities": [], "events": [], "relationships": [], "claims": []}

        batch_size = getattr(settings, "extractor_batch_size", 5)
        concurrency = getattr(settings, "extractor_max_concurrency", 3)

        if len(articles) <= batch_size:
            return self._extract_chunk(articles, offset=0)

        # Split into batches and execute concurrently
        from concurrent.futures import ThreadPoolExecutor, as_completed
        chunks = []
        for i in range(0, len(articles), batch_size):
            chunks.append((articles[i:i + batch_size], i))

        all_entities: list[dict] = []
        all_events: list[dict] = []
        all_relationships: list[dict] = []
        all_claims: list[dict] = []
        seen_entity_ids = set()

        workers = min(len(chunks), concurrency)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(self._extract_chunk, chunk_arts, offset) for chunk_arts, offset in chunks]
            for fut in as_completed(futures):
                try:
                    res = fut.result()
                    for ent in res.get("entities", []):
                        eid = ent.get("id")
                        if eid and eid not in seen_entity_ids:
                            seen_entity_ids.add(eid)
                            all_entities.append(ent)
                        elif not eid:
                            all_entities.append(ent)

                    all_events.extend(res.get("events", []))
                    all_relationships.extend(res.get("relationships", []))
                    all_claims.extend(res.get("claims", []))
                except Exception as exc:
                    print(f"[LLMExtractor] Batch execution error: {exc}", file=sys.stderr)

        return {
            "entities": all_entities,
            "events": all_events,
            "relationships": all_relationships,
            "claims": all_claims,
        }
