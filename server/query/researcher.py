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
        )
        cleaned_topic = re.sub(r"\s+", " ", cleaned_topic).strip(" ?,.:;-")
        if cleaned_topic and len(cleaned_topic) > 3:
            search_queries.append(cleaned_topic)

        # Deduplicate search queries
        search_queries = list(dict.fromkeys(search_queries))[:2]

        print(f"[QueryResearcher] Topic search queries: {search_queries}, keywords: {keywords}")

        # 1. Fetch targeted topic articles from wire news (fast, targeted)
        topic_articles: list[Article] = []
        for sq in search_queries[:2]:
            t_arts = self.sources.search_topic_articles(sq, max_articles=4)
            topic_articles.extend(t_arts)

        # 2. Only fetch general RSS feeds if topic search returned 0 results
        if not topic_articles:
            general_articles = self.sources.discover_articles(max_per_feed=2)
            all_articles = general_articles
        else:
            all_articles = topic_articles

        seen_urls = set()
        deduped_articles: list[Article] = []
        for a in all_articles:
            if a.url not in seen_urls:
                seen_urls.add(a.url)
                deduped_articles.append(a)

        relevant_articles: list[Article] = []
        for art in deduped_articles:
            if art.feed_source and art.feed_source.startswith("topic_search:"):
                relevant_articles.append(art)
            else:
                text = f"{art.headline or ''} {art.summary or ''}".lower()
                if any(kw in text for kw in keywords):
                    relevant_articles.append(art)

        # Cap to research budget
        relevant_articles = relevant_articles[:4]

        # Filter against already known URLs and cap new articles to top 3 for fast extraction
        new_articles = [a for a in relevant_articles if not GraphStore.article_exists_by_url(a.url)][:3]
        print(f"[QueryResearcher] Found {len(relevant_articles)} relevant articles ({len(new_articles)} new).")

        entities_created = 0
        relationships_created = 0

        if new_articles:
            try:
                extracted = self.extractor.extract(new_articles)
                stats = self.writer.persist_extraction(new_articles, extracted)
                entities_created = stats.get("entities_created", 0)
                relationships_created = stats.get("relationships_created", 0)
            except Exception as e:
                print(f"[QueryResearcher] Extraction failed during research: {e}")

        # Determine reporting period
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        return {
            "research_triggered": True,
            "sources_searched": len(settings.rss_feeds),
            "articles_found": len(relevant_articles),
            "articles_new": len(new_articles),
            "entities_created": entities_created,
            "relationships_created": relationships_created,
            "reporting_period": f"Current reporting as of {today_str}",
            "limitations": [] if len(relevant_articles) > 0 else ["No new matching wire articles found for specific topic"],
            "articles": [
                {
                    "id": a.id,
                    "headline": a.headline,
                    "publisher": a.publisher or a.feed_source or "News Wire",
                    "url": a.url,
                    "published_at": (a.published_at.isoformat() if hasattr(a.published_at, "isoformat") else str(a.published_at)) if a.published_at else None,
                    "summary": a.summary,
                }
                for a in relevant_articles
            ],
        }
