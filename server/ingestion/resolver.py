"""Deterministic entity resolution and alias management."""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from server.database import GraphStore


def slugify(text: str) -> str:
    """Normalize a name to a clean lowercase slug identifier."""
    # Decompose unicode characters
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[-\s]+", "-", text).strip("-")
    return text


class EntityResolver:
    """Resolves raw entity names and IDs against persistent graph records."""

    @staticmethod
    def resolve_entity_id(raw_id: str, raw_label: str) -> str:
        """Resolve an entity identifier using slug normalization and alias lookup."""
        normalized_id = slugify(raw_id or raw_label)
        if not normalized_id:
            normalized_id = "unknown-entity"

        # Check if an entity with this exact ID already exists
        existing = GraphStore.get_entity(normalized_id)
        if existing:
            return normalized_id

        # Check if an existing entity has raw_label or raw_id as an alias
        search_matches = GraphStore.search_entities(raw_label, limit=5)
        for match in search_matches:
            # Check canonical name match (case-insensitive)
            if match["canonical_name"].strip().lower() == raw_label.strip().lower():
                return match["id"]
            # Check aliases
            for alias in match.get("aliases", []):
                if alias.strip().lower() == raw_label.strip().lower():
                    return match["id"]

        # If no confident match, return the new normalized slug
        return normalized_id

    @staticmethod
    def merge_aliases(existing_aliases: list[str], new_alias: Optional[str]) -> list[str]:
        if not new_alias or not new_alias.strip():
            return existing_aliases
        clean = new_alias.strip()
        if clean not in existing_aliases:
            return existing_aliases + [clean]
        return existing_aliases
