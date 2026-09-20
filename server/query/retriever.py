"""Graph retrieval module for structured queries, multi-hop reasoning, and evidence lookup."""
from __future__ import annotations

import json
from typing import Optional

from server.database import GraphStore, get_db


class GraphRetriever:
    """Retrieves structured graph context, multi-hop relationships, and supporting evidence."""

    @staticmethod
    def identify_entities_in_text(text: str) -> list[dict]:
        """Identify candidate entities from text using exact and fuzzy matching."""
        words = [w.strip("?,.:;\"'()[]{}") for w in text.split() if len(w) > 2]
        candidates: dict[str, dict] = {}
        stop_words = {
            "the", "and", "for", "are", "with", "from", "that", "this", "what",
            "give", "tell", "about", "latest", "today", "yesterday", "update",
            "updates", "current", "recent", "major", "news", "developments", "between"
        }

        # Prioritize 3-word, then 2-word, then 1-word phrases
        n = len(words)
        phrases = []
        for length in (3, 2, 1):
            for i in range(n - length + 1):
                phrase = " ".join(words[i:i + length])
                if phrase.lower() not in stop_words:
                    phrases.append(phrase)

        # Deduplicate while preserving order, cap at 15 queries
        seen = set()
        deduped = []
        for p in phrases:
            if p.lower() not in seen:
                seen.add(p.lower())
                deduped.append(p)

        for phrase in deduped[:15]:
            matches = GraphStore.search_entities(phrase, limit=3)
            for m in matches:
                candidates[m["id"]] = m

        return list(candidates.values())

    @staticmethod
    def get_multi_hop_context(entity_ids: list[str], max_hops: int = 2) -> dict:
        """Perform multi-hop traversal to gather connected entities and relationships."""
        return GraphStore.get_subgraph(entity_ids, max_hops=max_hops)

    @staticmethod
    def get_events_for_entities(entity_ids: list[str], limit: int = 10) -> list[dict]:
        """Find events involving the target entities."""
        if not entity_ids:
            return []

        with get_db() as conn:
            placeholders = ",".join(["?"] * len(entity_ids))
            # Check direct entity_event_links or relationships to events
            query = f"""
            SELECT DISTINCT ev.* FROM events ev
            LEFT JOIN entity_event_links eel ON ev.id = eel.event_id
            WHERE eel.entity_id IN ({placeholders})
               OR ev.summary LIKE ?
            ORDER BY ev.updated_at DESC LIMIT ?
            """
            params = list(entity_ids) + [f"%{entity_ids[0]}%", limit]
            rows = conn.execute(query, params).fetchall()
            events = []
            for r in rows:
                d = dict(r)
                d["metadata"] = json.loads(d.get("metadata") or "{}")
                events.append(d)
            return events

    @staticmethod
    def get_claims_and_evidence(entity_ids: list[str], limit: int = 15) -> list[dict]:
        """Retrieve factual claims and supporting articles for the entities."""
        if not entity_ids:
            return []

        with get_db() as conn:
            placeholders = ",".join(["?"] * len(entity_ids))
            query = f"""
            SELECT c.*, a.headline, a.publisher, a.url, a.published_at
            FROM claims c
            JOIN articles a ON c.source_article_id = a.id
            WHERE c.subject_entity_id IN ({placeholders})
               OR c.object_entity_id IN ({placeholders})
            ORDER BY c.observed_at DESC LIMIT ?
            """
            params = list(entity_ids) + list(entity_ids) + [limit]
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def get_recent_articles_for_entities(entity_ids: list[str], limit: int = 10) -> list[dict]:
        """Retrieve recent articles associated with these entities through claims or relationships."""
        if not entity_ids:
            # Fallback to general recent articles
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT * FROM articles ORDER BY ingested_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]

        with get_db() as conn:
            placeholders = ",".join(["?"] * len(entity_ids))
            query = f"""
            SELECT DISTINCT a.* FROM articles a
            LEFT JOIN claims c ON a.id = c.source_article_id
            LEFT JOIN relationships r ON a.id = r.source_article_id
            WHERE c.subject_entity_id IN ({placeholders})
               OR c.object_entity_id IN ({placeholders})
               OR r.source_id IN ({placeholders})
               OR r.target_id IN ({placeholders})
            ORDER BY a.ingested_at DESC LIMIT ?
            """
            params = list(entity_ids) * 4 + [limit]
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
