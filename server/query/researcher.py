"""Query-triggered fresh news research engine."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from server.config import settings
from server.database import GraphStore
from server.ingestion.extractor import LLMExtractor
from server.ingestion.sources import RSSConnector
from server.ingestion.writer import GraphWriter
from server.models import Article

TEMPORAL_KEYWORDS = {
    "today", "yesterday", "latest", "breaking", "update", "updates",
    "recent", "current", "now", "this week", "last night", "new", "ongoing"
}


class QueryResearcher:
    """Discovers fresh news and expands graph evidence when a user query requires it."""

    def __init__(self):
        self.sources = RSSConnector()
        self.extractor = LLMExtractor()
        self.writer = GraphWriter()

    def should_trigger_research(
        self,
        question: str,
        matched_entities: list[dict],
        force: bool = False,
    ) -> tuple[bool, str]:
        """Determine whether fresh news research is necessary."""
        # 1. User explicitly requested forced research via UI
        if force:
            return True, "User requested forced live news research."

        # 2. If entities are present in knowledge graph, serve immediately from graph
        # This provides fast Graph RAG responses (~5-10s) without blocking on slow web crawlers
        if matched_entities:
            return False, "Existing knowledge graph context is available."

        # 3. Only if zero entities match the query, discover from news wire
        return True, "No matching entities found in local graph; discovering from news wire."

    def perform_research(
        self,
        question: str,
        matched_entities: list[dict],
    ) -> dict[str, Any]:
        """Execute fresh news research for the given query."""
        keywords = [
            (ent.get("canonical_name") or ent.get("label") or ent.get("id", "")).lower()
            for ent in matched_entities
            if (ent.get("canonical_name") or ent.get("label") or ent.get("id"))
        ]
        # Extract proper nouns or capitalized terms from question
        prop_nouns = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", question)

        # Build search queries from proper nouns and clean topic text
        search_queries = []
        if prop_nouns:
            search_queries.append(" ".join(prop_nouns[:3]))
        
        # Clean question of common conversational filler
        cleaned_topic = re.sub(
            r"(?i)\b(give me|what are|today'?s|latest|current|major|updates?|on|in|developments?|tell me about|summarize|explain)\b",
            " ", question