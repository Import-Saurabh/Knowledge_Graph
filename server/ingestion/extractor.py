"""LLM-based entity, event, relationship, and evidence extraction."""
from __future__ import annotations

import json
import logging
import re
import sys
from typing import Any

from anthropic import Anthropic

from server.config import settings
from server.models import Article

logger = logging.getLogger(__name__)

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
        """Extract graph elements from a single chunk of articles with index offset adjustment.

        Returns a dict with 'entities', 'events', 'relationships', 'claims',
        and '_failed' (bool) so callers can distinguish empty extraction from
        a hard failure.
        """
        empty = {"entities": [], "events": [], "relationships": [], "claims": []}
        if not chunk_articles:
            return empty

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

                # Bug #13 fix: handle thinking blocks (e.g. MiniMax-M3.1-Flash).
                # Walk through all content blocks and find the first text block.
                raw_text = ""
                for block in response.content:
                    if getattr(block, "type", None) == "text" and getattr(block, "text", None):
                        raw_text = block.text.strip()
                        break
                if not raw_text:
                    # Fallback: try legacy .text on first block
                    raw_text = (getattr(response.content[0], "text", "") or "").strip()

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

                # Bug #7 fix: safely coerce article_index to int so a
                # non-numeric value doesn't crash the whole batch.
                def _safe_int(val: Any, default: int = 1) -> int:
                    try:
                        return int(val)
                    except (TypeError, ValueError):
                        return default

                # Re-map 1-based article_index to match global article list
                for ev in events:
                    if "article_index" in ev:
                        ev["article_index"] = _safe_int(ev["article_index"]) + offset
                for rel in relationships:
                    if "article_index" in rel:
                        rel["article_index"] = _safe_int(rel["article_index"]) + offset
                for cl in claims:
                    if "article_index" in cl:
                        cl["article_index"] = _safe_int(cl["article_index"]) + offset

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
                logger.error(f"[LLMExtractor] Error during chunk extraction (offset {offset}): {e}")
                # Bug #1 fix: mark as failed so the pipeline can track it
                return {**empty, "_failed": True}

    def extract(self, articles: list[Article]) -> dict[str, Any]:
        """Perform structured extraction on articles, using parallel chunking for low latency.

        Returns dict with 'entities', 'events', 'relationships', 'claims',
        and 'failed_article_count' so the pipeline can record partial failures.
        """
        empty = {"entities": [], "events": [], "relationships": [], "claims": [], "failed_article_count": 0}
        if not articles:
            return empty

        batch_size = getattr(settings, "extractor_batch_size", 5)
        concurrency = getattr(settings, "extractor_max_concurrency", 3)

        if len(articles) <= batch_size:
            result = self._extract_chunk(articles, offset=0)
            is_failed = result.pop("_failed", False)
            for a in articles:
                a.extraction_status = "failed" if is_failed else "extracted"
            result["failed_article_count"] = len(articles) if is_failed else 0
            return result

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
        failed_article_count = 0

        workers = min(len(chunks), concurrency)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self._extract_chunk, chunk_arts, offset): (chunk_arts, offset)
                for chunk_arts, offset in chunks
            }
            for fut in as_completed(futures):
                chunk_arts, offset = futures[fut]
                try:
                    res = fut.result()
                    if res.pop("_failed", False):
                        for a in chunk_arts:
                            a.extraction_status = "failed"
                        failed_article_count += len(chunk_arts)
                        continue

                    for a in chunk_arts:
                        a.extraction_status = "extracted"

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
                    logger.error(f"[LLMExtractor] Batch execution error: {exc}")
                    for a in chunk_arts:
                        a.extraction_status = "failed"
                    failed_article_count += len(chunk_arts)

        return {
            "entities": all_entities,
            "events": all_events,
            "relationships": all_relationships,
            "claims": all_claims,
            "failed_article_count": failed_article_count,
        }
