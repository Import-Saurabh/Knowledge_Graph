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

    def extract(self, articles: list[Article]) -> dict[str, Any]:
        """Perform structured extraction on a batch of articles."""
        if not articles:
            return {"entities": [], "events": [], "relationships": [], "claims": []}

        articles_text = "\n\n".join(
            f"ARTICLE {i + 1} ({a.publisher or 'Unknown Source'} - {a.published_at or 'Today'}):\n"
            f"Title: {a.headline}\n"
            f"Summary: {a.summary or a.content_excerpt or ''}\n"
            f"URL: {a.url}"
            for i, a in enumerate(articles)
        )

        prompt = (
            f"Extract the news knowledge graph, events, relationships, and claims from these {len(articles)} articles:\n\n"
            f"{articles_text}"
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=8192,
                system=EXTRACTION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_text = response.content[0].text.strip()
            # Strip markdown code blocks if wrapped
            if raw_text.startswith("```"):
                raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                raw_text = re.sub(r"\s*```$", "", raw_text)

            data = json.loads(raw_text)
            return {
                "entities": data.get("entities", []),
                "events": data.get("events", []),
                "relationships": data.get("relationships", []),
                "claims": data.get("claims", []),
            }
        except Exception as e:
            print(f"[LLMExtractor] Error during extraction: {e}", file=sys.stderr)
            raise
