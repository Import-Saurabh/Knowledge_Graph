"""Transactional database writer for graph entities, events, relationships, and claims."""
from __future__ import annotations

import json
import uuid
from typing import Any

from server.config import settings
from server.database import GraphStore, get_db
from server.ingestion.resolver import EntityResolver
from server.models import Article, Claim, Entity, Event, Relationship, utc_now_iso


class GraphWriter:
    """Writes extracted entities, events, relationships, and evidence to SQLite store."""

    @staticmethod
    def persist_extraction(
        articles: list[Article],
        extracted_data: dict[str, Any],
    ) -> dict[str, int]:
        """Save raw extraction with entity resolution and relationship linking."""
        now = utc_now_iso()
        stats = {
            "entities_created": 0,
            "entities_updated": 0,
            "events_created": 0,
            "relationships_created": 0,
            "claims_created": 0,
        }

        # 1. Map article index (1-based) to article instance
        article_map: dict[int, Article] = {i + 1: a for i, a in enumerate(articles)}

        # 2. Persist articles first
        for a in articles:
            GraphStore.upsert_article(a)

        # 3. Resolve and upsert entities
        id_remap: dict[str, str] = {}
        for ent_raw in extracted_data.get("entities", []):
            raw_id = ent_raw.get("id", "")
            raw_label = ent_raw.get("label", raw_id)
            ent_type = ent_raw.get("type", "concept")
            desc = ent_raw.get("description", "")
            aliases = ent_raw.get("aliases", [])

            resolved_id = EntityResolver.resolve_entity_id(raw_id, raw_label)
            id_remap[raw_id] = resolved_id

            existing = GraphStore.get_entity(resolved_id)
            if existing:
                merged_aliases = existing.get("aliases", [])
                for al in aliases + [raw_label]:
                    merged_aliases = EntityResolver.merge_aliases(merged_aliases, al)

                entity_obj = Entity(
                    id=resolved_id,
                    entity_type=ent_type or existing["entity_type"],
                    canonical_name=existing["canonical_name"] or raw_label,
                    description=desc or existing.get("description"),
                    aliases=merged_aliases,
                    external_ids=existing.get("external_ids", {}),
                    first_observed_at=existing["first_observed_at"],
                    updated_at=now,
                )
                GraphStore.upsert_entity(entity_obj)
                stats["entities_updated"] += 1
            else:
                entity_obj = Entity(
                    id=resolved_id,
                    entity_type=ent_type,
                    canonical_name=raw_label,
                    description=desc,
                    aliases=list(set(aliases + [raw_label])),
                    first_observed_at=now,
                    updated_at=now,
                )
                GraphStore.upsert_entity(entity_obj)
                stats["entities_created"] += 1

        # 4. Upsert events
        for ev_raw in extracted_data.get("events", []):
            ev_id = ev_raw.get("id") or str(uuid.uuid4())
            ev_type = ev_raw.get("event_type", "incident")
            summary = ev_raw.get("summary", "")
            ev_time = ev_raw.get("event_time")
            loc = ev_raw.get("location")
            idx = ev_raw.get("article_index", 1)
            source_art = article_map.get(idx)

            event_obj = Event(
                id=ev_id,
                event_type=ev_type,
                summary=summary,
                event_time=ev_time,
                location=loc,
                first_observed_at=now,
                updated_at=now,
                metadata={"source_article_url": source_art.url if source_art else None},
            )
            GraphStore.upsert_event(event_obj)
            stats["events_created"] += 1

        # 5. Upsert relationships
        for rel_raw in extracted_data.get("relationships", []):
            s_raw = rel_raw.get("source", "")
            t_raw = rel_raw.get("target", "")
            r_type = rel_raw.get("type", "RELATED_TO").upper()
            desc = rel_raw.get("description", "")
            idx = rel_raw.get("article_index", 1)
            source_art = article_map.get(idx)

            s_resolved = id_remap.get(s_raw, s_raw)
            t_resolved = id_remap.get(t_raw, t_raw)

            if s_resolved and t_resolved and s_resolved != t_resolved:
                rel_id = f"{s_resolved}_{r_type}_{t_resolved}"
                rel_obj = Relationship(
                    id=rel_id,
                    source_id=s_resolved,
                    target_id=t_resolved,
                    relationship_type=r_type,
                    description=desc,
                    source_article_id=source_art.id if source_art else None,
                    first_observed_at=now,
                    updated_at=now,
                )
                GraphStore.upsert_relationship(rel_obj)
                stats["relationships_created"] += 1

        # 6. Upsert claims
        for claim_raw in extracted_data.get("claims", []):
            text = claim_raw.get("claim_text", "")
            if not text:
                continue
            idx = claim_raw.get("article_index", 1)
            source_art = article_map.get(idx)
            if not source_art:
                continue

            sub_resolved = id_remap.get(claim_raw.get("subject", ""), None)
            obj_resolved = id_remap.get(claim_raw.get("object", ""), None)

            claim_obj = Claim(
                id=str(uuid.uuid4()),
                claim_text=text,
                subject_entity_id=sub_resolved,
                predicate=claim_raw.get("predicate"),
                object_entity_id=obj_resolved,
                source_article_id=source_art.id,
                attribution=claim_raw.get("attribution"),
                observed_at=now,
            )
            # Store in DB
            with get_db() as conn:
                conn.execute(
                    """
                    INSERT INTO claims (id, claim_text, subject_entity_id, predicate, object_entity_id, source_article_id, attribution, claim_type, confidence, event_id, observed_at, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        claim_obj.id,
                        claim_obj.claim_text,
                        claim_obj.subject_entity_id,
                        claim_obj.predicate,
                        claim_obj.object_entity_id,
                        claim_obj.source_article_id,
                        claim_obj.attribution,
                        claim_obj.claim_type,
                        claim_obj.confidence,
                        claim_obj.event_id,
                        claim_obj.observed_at,
                        json.dumps(claim_obj.metadata),
                    ),
                )
                conn.commit()
            stats["claims_created"] += 1

        # 7. Write updated graph.json snapshot for 3D visualizer
        GraphWriter.export_graph_snapshot()

        return stats

    @staticmethod
    def export_graph_snapshot() -> None:
        """Export current graph state from SQLite to graph.json for static visualizer compatibility."""
        try:
            graph_data = GraphStore.get_all_graph_data(limit_nodes=500)
            graph_file = settings.data_dir.parent / "graph.json"
            with open(graph_file, "w", encoding="utf-8") as f:
                json.dump(graph_data, f, indent=2)
            print(f"[GraphWriter] Exported snapshot to {graph_file} ({len(graph_data['nodes'])} nodes, {len(graph_data['links'])} links)")
        except Exception as e:
            print(f"[GraphWriter] Warning: could not export snapshot: {e}")
