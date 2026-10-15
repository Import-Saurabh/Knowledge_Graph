"""Embedded Kùzu graph database engine providing sub-millisecond Cypher multi-hop traversals."""
from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

import kuzu

from server.config import settings

logger = logging.getLogger(__name__)

_local = threading.local()
_kuzu_db_instance: Optional[kuzu.Database] = None
_init_lock = threading.Lock()


class KuzuGraphEngine:
    """Embedded in-memory/columnar graph store accelerated by Kùzu."""

    @classmethod
    def get_database(cls, db_path: Optional[Path | str] = None) -> kuzu.Database:
        """Get or initialize the shared Kùzu Database instance."""
        global _kuzu_db_instance
        if _kuzu_db_instance is None:
            with _init_lock:
                if _kuzu_db_instance is None:
                    target_path = Path(db_path or settings.kuzu_db_path)
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    cls._init_database(target_path)
        return _kuzu_db_instance

    @classmethod
    def _init_database(cls, target_path: Path) -> None:
        global _kuzu_db_instance
        path_str = str(target_path)
        _kuzu_db_instance = kuzu.Database(path_str)
        conn = kuzu.Connection(_kuzu_db_instance)

        # Initialize Node schema
        try:
            conn.execute(
                "CREATE NODE TABLE Entity(id STRING, canonical_name STRING, entity_type STRING, description STRING, PRIMARY KEY (id))"
            )
        except Exception:
            pass

        # Initialize Rel schema
        try:
            conn.execute(
                "CREATE REL TABLE RelatesTo(FROM Entity TO Entity, relationship_type STRING, description STRING)"
            )
        except Exception:
            pass

    @classmethod
    def get_connection(cls) -> kuzu.Connection:
        """Return a thread-local Kùzu Connection."""
        db = cls.get_database()
        if not hasattr(_local, "kuzu_conn") or _local.kuzu_conn is None:
            _local.kuzu_conn = kuzu.Connection(db)
        return _local.kuzu_conn

    @classmethod
    def reset(cls, target_path: Optional[Path | str] = None) -> None:
        """Reset the singleton instance (primarily for tests)."""
        global _kuzu_db_instance
        with _init_lock:
            _kuzu_db_instance = None
            if hasattr(_local, "kuzu_conn"):
                _local.kuzu_conn = None
        if target_path:
            cls.get_database(target_path)

    @classmethod
    def upsert_entity(
        cls,
        entity_id: str,
        canonical_name: str,
        entity_type: str = "concept",
        description: str = "",
    ) -> None:
        """Insert or update an entity node in Kùzu."""
        try:
            conn = cls.get_connection()
            cypher = """
            MERGE (e:Entity {id: $id})
            ON CREATE SET e.canonical_name = $name, e.entity_type = $type, e.description = $description
            ON MATCH SET e.canonical_name = $name, e.entity_type = $type, e.description = $description
            """
            conn.execute(
                cypher,
                {
                    "id": str(entity_id),
                    "name": str(canonical_name or entity_id),
                    "type": str(entity_type or "concept"),
                    "description": str(description or ""),
                },
            )
        except Exception as e:
            logger.warning(f"[KuzuGraphEngine] Error upserting entity {entity_id}: {e}")

    @classmethod
    def upsert_relationship(
        cls,
        source_id: str,
        target_id: str,
        relationship_type: str = "RELATED_TO",
        description: str = "",
    ) -> None:
        """Insert or update a relationship edge in Kùzu."""
        if not source_id or not target_id or source_id == target_id:
            return
        try:
            conn = cls.get_connection()
            # Ensure endpoints exist
            conn.execute(
                "MERGE (a:Entity {id: $id}) ON CREATE SET a.canonical_name = $id, a.entity_type = 'concept', a.description = ''",
                {"id": str(source_id)},
            )
            conn.execute(
                "MERGE (b:Entity {id: $id}) ON CREATE SET b.canonical_name = $id, b.entity_type = 'concept', b.description = ''",
                {"id": str(target_id)},
            )

            cypher = """
            MATCH (a:Entity {id: $s}), (b:Entity {id: $t})
            MERGE (a)-[r:RelatesTo {relationship_type: $rtype}]->(b)
            ON CREATE SET r.description = $description
            ON MATCH SET r.description = $description
            """
            conn.execute(
                cypher,
                {
                    "s": str(source_id),
                    "t": str(target_id),
                    "rtype": str(relationship_type or "RELATED_TO").upper(),
                    "description": str(description or ""),
                },
            )
        except Exception as e:
            logger.warning(f"[KuzuGraphEngine] Error upserting relationship {source_id}->{target_id}: {e}")

    @classmethod
    def get_subgraph(cls, entity_ids: list[str], max_hops: int = 1) -> dict[str, list]:
        """Perform vectorized multi-hop neighborhood traversal in Kùzu."""
        if not entity_ids:
            return {"nodes": [], "links": []}

        safe_hops = min(max(1, int(max_hops)), 3)
        conn = cls.get_connection()

        nodes_map: dict[str, dict[str, str]] = {}
        target_entity_ids = [str(eid) for eid in entity_ids if eid]

        # 1. Fetch seed entities
        for eid in target_entity_ids:
            try:
                res = conn.execute(
                    "MATCH (e:Entity {id: $id}) RETURN e.id, e.canonical_name, e.entity_type, e.description",
                    {"id": eid},
                )
                if res.has_next():
                    row = res.get_next()
                    nodes_map[row[0]] = {
                        "id": row[0],
                        "label": row[1] or row[0],
                        "type": row[2] or "concept",
                        "description": row[3] or "",
                    }
            except Exception:
                pass

        # 2. Multi-hop traversal using Cypher variable-length paths
        for eid in target_entity_ids:
            try:
                query = f"""
                MATCH (a:Entity {{id: $id}})-[r:RelatesTo*1..{safe_hops}]-(b:Entity)
                RETURN DISTINCT b.id, b.canonical_name, b.entity_type, b.description
                """
                res = conn.execute(query, {"id": eid})
                while res.has_next():
                    row = res.get_next()
                    if row[0] not in nodes_map:
                        nodes_map[row[0]] = {
                            "id": row[0],
                            "label": row[1] or row[0],
                            "type": row[2] or "concept",
                            "description": row[3] or "",
                        }
            except Exception as e:
                logger.warning(f"[KuzuGraphEngine] Traversal error for {eid}: {e}")

        all_node_ids = list(nodes_map.keys())
        if not all_node_ids:
            return {"nodes": [], "links": []}

        # 3. Retrieve all connecting edges among discovered nodes
        links: list[dict[str, str]] = []
        try:
            rel_query = """
            MATCH (a:Entity)-[r:RelatesTo]->(b:Entity)
            WHERE a.id IN $node_ids AND b.id IN $node_ids
            RETURN a.id, b.id, r.relationship_type, r.description
            """
            res = conn.execute(rel_query, {"node_ids": all_node_ids})
            seen_edges = set()
            while res.has_next():
                row = res.get_next()
                s, t, rtype, desc = row[0], row[1], row[2], row[3]
                edge_key = (s, t, rtype)
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    links.append({
                        "source": s,
                        "target": t,
                        "type": rtype,
                        "description": desc or "",
                    })
        except Exception as e:
            logger.warning(f"[KuzuGraphEngine] Edge retrieval error: {e}")

        return {
            "nodes": list(nodes_map.values()),
            "links": links,
        }

    @classmethod
    def sync_from_sqlite(cls, conn: sqlite3.Connection) -> None:
        """Synchronize existing entities and relationships from SQLite into Kùzu."""
        try:
            # Sync entities
            entity_rows = conn.execute(
                "SELECT id, canonical_name, entity_type, description FROM entities"
            ).fetchall()
            for r in entity_rows:
                cls.upsert_entity(
                    entity_id=r["id"],
                    canonical_name=r["canonical_name"],
                    entity_type=r["entity_type"],
                    description=r["description"] or "",
                )

            # Sync relationships
            rel_rows = conn.execute(
                "SELECT source_id, target_id, relationship_type, description FROM relationships"
            ).fetchall()
            for r in rel_rows:
                cls.upsert_relationship(
                    source_id=r["source_id"],
                    target_id=r["target_id"],
                    relationship_type=r["relationship_type"],
                    description=r["description"] or "",
                )
            logger.info(
                f"[KuzuGraphEngine] Synchronized {len(entity_rows)} entities and {len(rel_rows)} relationships from SQLite."
            )
        except Exception as e:
            logger.warning(f"[KuzuGraphEngine] Sync from SQLite failed: {e}")
