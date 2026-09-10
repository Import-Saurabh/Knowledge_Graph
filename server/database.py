"""SQLite persistent database layer with FTS5 and graph traversal capabilities."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Optional

from server.config import settings
from server.models import (
    Article,
    Claim,
    Conversation,
    Entity,
    Event,
    IngestionJob,
    Message,
    Relationship,
    utc_now_iso,
)

_local = threading.local()


def get_db_connection() -> sqlite3.Connection:
    """Thread-local database connection with row factory and WAL mode."""
    if not hasattr(_local, "conn") or _local.conn is None:
        conn = sqlite3.connect(
            str(settings.db_path),
            check_same_thread=False,
            timeout=30.0,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        _local.conn = conn
    return _local.conn


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = get_db_connection()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise


SCHEMA_SQL = """
-- Entities table
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    description TEXT,
    aliases TEXT DEFAULT '[]',
    external_ids TEXT DEFAULT '{}',
    first_observed_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata TEXT DEFAULT '{}'
);

-- Events table
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    event_time TEXT,
    event_time_precision TEXT DEFAULT 'day',
    location TEXT,
    status TEXT DEFAULT 'reported',
    confidence REAL DEFAULT 0.8,
    first_observed_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata TEXT DEFAULT '{}'
);

-- Articles / Sources table
CREATE TABLE IF NOT EXISTS articles (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    url_hash TEXT NOT NULL,
    publisher TEXT,
    headline TEXT,
    summary TEXT,
    content_excerpt TEXT,
    content_hash TEXT,
    author TEXT,
    language TEXT DEFAULT 'en',
    published_at TEXT,
    ingested_at TEXT NOT NULL,
    feed_source TEXT,
    extraction_status TEXT DEFAULT 'pending',
    metadata TEXT DEFAULT '{}'
);

-- Claims / Evidence table
CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY,
    claim_text TEXT NOT NULL,
    subject_entity_id TEXT,
    predicate TEXT,
    object_entity_id TEXT,
    source_article_id TEXT NOT NULL,
    attribution TEXT,
    claim_type TEXT DEFAULT 'media_report',
    confidence REAL DEFAULT 0.8,
    event_id TEXT,
    observed_at TEXT NOT NULL,
    metadata TEXT DEFAULT '{}',
    FOREIGN KEY (source_article_id) REFERENCES articles(id) ON DELETE CASCADE,
    FOREIGN KEY (subject_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
    FOREIGN KEY (object_entity_id) REFERENCES entities(id) ON DELETE SET NULL,
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE SET NULL
);

-- Relationships table
CREATE TABLE IF NOT EXISTS relationships (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    description TEXT,
    source_article_id TEXT,
    first_observed_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata TEXT DEFAULT '{}',
    UNIQUE(source_id, target_id, relationship_type)
);

-- Entity-Event participation links
CREATE TABLE IF NOT EXISTS entity_event_links (
    entity_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    role TEXT DEFAULT 'participant',
    source_article_id TEXT,
    PRIMARY KEY (entity_id, event_id, role),
    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
);

-- Conversations table
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT DEFAULT 'New Conversation',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Messages table
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    citations TEXT DEFAULT '[]',
    entity_ids TEXT DEFAULT '[]',
    event_ids TEXT DEFAULT '[]',
    research_metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

-- Ingestion jobs history table
CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    trigger TEXT,
    articles_discovered INTEGER DEFAULT 0,
    articles_processed INTEGER DEFAULT 0,
    articles_skipped INTEGER DEFAULT 0,
    articles_failed INTEGER DEFAULT 0,
    entities_created INTEGER DEFAULT 0,
    entities_updated INTEGER DEFAULT 0,
    events_created INTEGER DEFAULT 0,
    relationships_created INTEGER DEFAULT 0,
    error_details TEXT,
    metadata TEXT DEFAULT '{}'
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(canonical_name);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_time ON events(event_time);
CREATE INDEX IF NOT EXISTS idx_articles_url_hash ON articles(url_hash);
CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at);
CREATE INDEX IF NOT EXISTS idx_relationships_source ON relationships(source_id);
CREATE INDEX IF NOT EXISTS idx_relationships_target ON relationships(target_id);
CREATE INDEX IF NOT EXISTS idx_relationships_type ON relationships(relationship_type);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_claims_article ON claims(source_article_id);
CREATE INDEX IF NOT EXISTS idx_claims_subject ON claims(subject_entity_id);
CREATE INDEX IF NOT EXISTS idx_claims_event ON claims(event_id);
"""

FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
    id UNINDEXED,
    canonical_name,
    description,
    aliases
);

CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
    id UNINDEXED,
    summary,
    location
);
"""


def init_db(db_path: Optional[Path] = None) -> None:
    """Initialize database schema, indexes, and full text search tables."""
    path = db_path or settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)

    with get_db() as conn:
        conn.executescript(SCHEMA_SQL)
        try:
            conn.executescript(FTS_SQL)
        except sqlite3.OperationalError:
            # FTS5 might already exist or need table rebuild
            pass
        conn.commit()

    seed_from_graph_json_if_empty()


def seed_from_graph_json_if_empty() -> None:
    """If database has 0 entities, seed from existing graph.json to preserve historical baseline."""
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        if count > 0:
            return

        graph_file = settings.data_dir.parent / "graph.json"
        if not graph_file.exists():
            return

        try:
            with open(graph_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            now = data.get("generated_at", utc_now_iso())
            nodes = data.get("nodes", [])
            links = data.get("links", [])

            cursor = conn.cursor()
            for node in nodes:
                nid = node.get("id")
                label = node.get("label", nid)
                ntype = node.get("type", "concept")
                desc = node.get("description", "")
                if nid:
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO entities (id, entity_type, canonical_name, description, aliases, first_observed_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (nid, ntype, label, desc, json.dumps([label]), now, now),
                    )
                    # Index in FTS
                    try:
                        cursor.execute(
                            "INSERT OR IGNORE INTO entities_fts (id, canonical_name, description, aliases) VALUES (?, ?, ?, ?)",
                            (nid, label, desc, json.dumps([label])),
                        )
                    except Exception:
                        pass

            for link in links:
                s = link.get("source")
                t = link.get("target")
                ltype = link.get("type", "RELATED_TO")
                desc = link.get("description", "")
                if s and t and s != t:
                    lid = f"{s}_{ltype}_{t}"
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO relationships (id, source_id, target_id, relationship_type, description, first_observed_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (lid, s, t, ltype, desc, now, now),
                    )

            conn.commit()
            print(f"Database seeded from graph.json: {len(nodes)} entities, {len(links)} relationships.")
        except Exception as e:
            print(f"Notice: Could not seed from graph.json: {e}")


# ---------------------------------------------------------------------------
# Data Access Methods
# ---------------------------------------------------------------------------

class GraphStore:
    """Data access repository for entities, events, relationships, articles, and chat."""

    @staticmethod
    def upsert_entity(entity: Entity) -> None:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO entities (id, entity_type, canonical_name, description, aliases, external_ids, first_observed_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    entity_type = excluded.entity_type,
                    canonical_name = excluded.canonical_name,
                    description = COALESCE(excluded.description, entities.description),
                    aliases = excluded.aliases,
                    external_ids = excluded.external_ids,
                    updated_at = excluded.updated_at,
                    metadata = excluded.metadata
                """,
                (
                    entity.id,
                    entity.entity_type,
                    entity.canonical_name,
                    entity.description,
                    json.dumps(entity.aliases),
                    json.dumps(entity.external_ids),
                    entity.first_observed_at,
                    entity.updated_at,
                    json.dumps(entity.metadata),
                ),
            )
            # Sync FTS
            try:
                conn.execute("DELETE FROM entities_fts WHERE id = ?", (entity.id,))
                conn.execute(
                    "INSERT INTO entities_fts (id, canonical_name, description, aliases) VALUES (?, ?, ?, ?)",
                    (entity.id, entity.canonical_name, entity.description or "", json.dumps(entity.aliases)),
                )
            except Exception:
                pass
            conn.commit()

    @staticmethod
    def get_entity(entity_id: str) -> Optional[dict]:
        with get_db() as conn:
            row = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["aliases"] = json.loads(d.get("aliases") or "[]")
            d["external_ids"] = json.loads(d.get("external_ids") or "{}")
            d["metadata"] = json.loads(d.get("metadata") or "{}")
            return d

    @staticmethod
    def search_entities(query: str, limit: int = 20) -> list[dict]:
        with get_db() as conn:
            # Try FTS first
            try:
                clean_query = query.replace('"', '""').strip()
                match_expr = f'"{clean_query}"*'
                rows = conn.execute(
                    """
                    SELECT e.* FROM entities e
                    JOIN entities_fts fts ON e.id = fts.id
                    WHERE entities_fts MATCH ?
                    LIMIT ?
                    """,
                    (match_expr, limit),
                ).fetchall()
                if rows:
                    res = []
                    for r in rows:
                        d = dict(r)
                        d["aliases"] = json.loads(d.get("aliases") or "[]")
                        res.append(d)
                    return res
            except Exception:
                pass

            # Fallback to LIKE
            rows = conn.execute(
                """
                SELECT * FROM entities
                WHERE id LIKE ? OR canonical_name LIKE ? OR aliases LIKE ?
                LIMIT ?
                """,
                (f"%{query}%", f"%{query}%", f"%{query}%", limit),
            ).fetchall()
            res = []
            for r in rows:
                d = dict(r)
                d["aliases"] = json.loads(d.get("aliases") or "[]")
                res.append(d)
            return res

    @staticmethod
    def upsert_event(event: Event) -> None:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO events (id, event_type, summary, event_time, event_time_precision, location, status, confidence, first_observed_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    event_type = excluded.event_type,
                    summary = excluded.summary,
                    event_time = COALESCE(excluded.event_time, events.event_time),
                    event_time_precision = excluded.event_time_precision,
                    location = COALESCE(excluded.location, events.location),
                    status = excluded.status,
                    confidence = excluded.confidence,
                    updated_at = excluded.updated_at,
                    metadata = excluded.metadata
                """,
                (
                    event.id,
                    event.event_type,
                    event.summary,
                    event.event_time,
                    event.event_time_precision,
                    event.location,
                    event.status,
                    event.confidence,
                    event.first_observed_at,
                    event.updated_at,
                    json.dumps(event.metadata),
                ),
            )
            # Sync FTS
            try:
                conn.execute("DELETE FROM events_fts WHERE id = ?", (event.id,))
                conn.execute(
                    "INSERT INTO events_fts (id, summary, location) VALUES (?, ?, ?)",
                    (event.id, event.summary, event.location or ""),
                )
            except Exception:
                pass
            conn.commit()

    @staticmethod
    def get_event(event_id: str) -> Optional[dict]:
        with get_db() as conn:
            row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["metadata"] = json.loads(d.get("metadata") or "{}")
            return d

    @staticmethod
    def upsert_relationship(rel: Relationship) -> None:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO relationships (id, source_id, target_id, relationship_type, description, source_article_id, first_observed_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id, target_id, relationship_type) DO UPDATE SET
                    description = COALESCE(excluded.description, relationships.description),
                    source_article_id = COALESCE(excluded.source_article_id, relationships.source_article_id),
                    updated_at = excluded.updated_at,
                    metadata = excluded.metadata
                """,
                (
                    rel.id,
                    rel.source_id,
                    rel.target_id,
                    rel.relationship_type,
                    rel.description,
                    rel.source_article_id,
                    rel.first_observed_at,
                    rel.updated_at,
                    json.dumps(rel.metadata),
                ),
            )
            conn.commit()

    @staticmethod
    def get_relationships_for_entity(entity_id: str) -> list[dict]:
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT r.*,
                       e1.canonical_name as source_name, e1.entity_type as source_type,
                       e2.canonical_name as target_name, e2.entity_type as target_type
                FROM relationships r
                LEFT JOIN entities e1 ON r.source_id = e1.id
                LEFT JOIN entities e2 ON r.target_id = e2.id
                WHERE r.source_id = ? OR r.target_id = ?
                ORDER BY r.updated_at DESC
                """,
                (entity_id, entity_id),
            ).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def upsert_article(article: Article) -> bool:
        """Returns True if article was newly inserted, False if it was already known."""
        with get_db() as conn:
            existing = conn.execute("SELECT id FROM articles WHERE url = ?", (article.url,)).fetchone()
            if existing:
                return False

            conn.execute(
                """
                INSERT INTO articles (id, url, url_hash, publisher, headline, summary, content_excerpt, content_hash, author, language, published_at, ingested_at, feed_source, extraction_status, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    article.id,
                    article.url,
                    article.url_hash,
                    article.publisher,
                    article.headline,
                    article.summary,
                    article.content_excerpt,
                    article.content_hash,
                    article.author,
                    article.language,
                    article.published_at,
                    article.ingested_at,
                    article.feed_source,
                    article.extraction_status,
                    json.dumps(article.metadata),
                ),
            )
            conn.commit()
            return True

    @staticmethod
    def get_article(article_id: str) -> Optional[dict]:
        with get_db() as conn:
            row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
            return dict(row) if row else None

    @staticmethod
    def article_exists_by_url(url: str) -> bool:
        with get_db() as conn:
            row = conn.execute("SELECT 1 FROM articles WHERE url = ?", (url,)).fetchone()
            return row is not None

    @staticmethod
    def get_all_graph_data(limit_nodes: int = 500) -> dict:
        """Returns nodes and links formatted for the 3D force graph visualization."""
        with get_db() as conn:
            # Get nodes sorted by degree (number of connections)
            degree_rows = conn.execute(
                """
                SELECT entity_id, COUNT(*) as deg FROM (
                    SELECT source_id as entity_id FROM relationships
                    UNION ALL
                    SELECT target_id as entity_id FROM relationships
                ) GROUP BY entity_id
                """
            ).fetchall()
            degree_map = {r["entity_id"]: r["deg"] for r in degree_rows}

            entity_rows = conn.execute("SELECT * FROM entities").fetchall()
            total_entities = len(entity_rows)

            # Sort by degree descending and limit
            sorted_entities = sorted(
                entity_rows,
                key=lambda r: degree_map.get(r["id"], 0),
                reverse=True,
            )[:limit_nodes]

            active_ids = {r["id"] for r in sorted_entities}

            nodes = []
            for r in sorted_entities:
                deg = degree_map.get(r["id"], 0)
                nodes.append({
                    "id": r["id"],
                    "label": r["canonical_name"],
                    "canonical_name": r["canonical_name"],
                    "type": r["entity_type"],
                    "entity_type": r["entity_type"],
                    "description": r["description"] or "",
                    "val": max(4, deg ** 2 + 4),
                    "connection_count": deg,
                    "first_observed_at": r["first_observed_at"],
                })

            # Get links where both endpoints are in active_ids
            rel_rows = conn.execute("SELECT * FROM relationships").fetchall()
            total_rels = len(rel_rows)

            links = []
            for r in rel_rows:
                s = r["source_id"]
                t = r["target_id"]
                if s in active_ids and t in active_ids:
                    links.append({
                        "source": s,
                        "target": t,
                        "type": r["relationship_type"],
                        "description": r["description"] or "",
                    })

            # Find latest update time
            latest_row = conn.execute("SELECT MAX(updated_at) FROM entities").fetchone()
            latest_time = latest_row[0] if latest_row and latest_row[0] else utc_now_iso()

            return {
                "nodes": nodes,
                "links": links,
                "generated_at": latest_time,
                "entity_count": total_entities,
                "relationship_count": total_rels,
            }

    @staticmethod
    def get_subgraph(entity_ids: list[str], max_hops: int = 1) -> dict:
        """Retrieve the neighborhood subgraph centered on a set of entity IDs."""
        if not entity_ids:
            return {"nodes": [], "links": []}

        with get_db() as conn:
            # Use CTE to find connected nodes within max_hops
            placeholders = ",".join(["?"] * len(entity_ids))
            query = f"""
            WITH RECURSIVE neighborhood(node_id, depth) AS (
                SELECT id, 0 FROM entities WHERE id IN ({placeholders})
                UNION
                SELECT CASE WHEN r.source_id = n.node_id THEN r.target_id ELSE r.source_id END,
                       n.depth + 1
                FROM relationships r
                JOIN neighborhood n ON (r.source_id = n.node_id OR r.target_id = n.node_id)
                WHERE n.depth < ?
            )
            SELECT DISTINCT node_id FROM neighborhood;
            """
            params = list(entity_ids) + [max_hops]
            rows = conn.execute(query, params).fetchall()
            sub_node_ids = {r["node_id"] for r in rows}

            if not sub_node_ids:
                sub_node_ids = set(entity_ids)

            node_placeholders = ",".join(["?"] * len(sub_node_ids))
            node_rows = conn.execute(
                f"SELECT * FROM entities WHERE id IN ({node_placeholders})",
                list(sub_node_ids),
            ).fetchall()

            rel_rows = conn.execute(
                f"""
                SELECT * FROM relationships
                WHERE source_id IN ({node_placeholders}) AND target_id IN ({node_placeholders})
                """,
                list(sub_node_ids) + list(sub_node_ids),
            ).fetchall()

            nodes = [{
                "id": r["id"],
                "label": r["canonical_name"],
                "type": r["entity_type"],
                "description": r["description"] or "",
            } for r in node_rows]

            links = [{
                "source": r["source_id"],
                "target": r["target_id"],
                "type": r["relationship_type"],
                "description": r["description"] or "",
            } for r in rel_rows]

            return {"nodes": nodes, "links": links}

    # Conversation & Message Management
    @staticmethod
    def create_conversation(conv_id: str, title: str = "New Conversation") -> Conversation:
        now = utc_now_iso()
        with get_db() as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (conv_id, title, now, now),
            )
            conn.commit()
        return Conversation(id=conv_id, title=title, created_at=now, updated_at=now)

    @staticmethod
    def get_conversation(conv_id: str) -> Optional[dict]:
        with get_db() as conn:
            row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
            if not row:
                return None
            conv = dict(row)
            msg_rows = conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
                (conv_id,),
            ).fetchall()
            messages = []
            for m in msg_rows:
                md = dict(m)
                md["citations"] = json.loads(md.get("citations") or "[]")
                md["entity_ids"] = json.loads(md.get("entity_ids") or "[]")
                md["event_ids"] = json.loads(md.get("event_ids") or "[]")
                md["research_metadata"] = json.loads(md.get("research_metadata") or "{}")
                messages.append(md)
            conv["messages"] = messages
            return conv

    @staticmethod
    def list_conversations(limit: int = 50) -> list[dict]:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def save_message(message: Message) -> None:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO messages (id, conversation_id, role, content, citations, entity_ids, event_ids, research_metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.id,
                    message.conversation_id,
                    message.role,
                    message.content,
                    json.dumps(message.citations),
                    json.dumps(message.entity_ids),
                    json.dumps(message.event_ids),
                    json.dumps(message.research_metadata),
                    message.created_at,
                ),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (message.created_at, message.conversation_id),
            )
            conn.commit()

    # Ingestion Job Management
    @staticmethod
    def record_job(job: IngestionJob) -> None:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO ingestion_jobs (
                    id, job_type, status, started_at, completed_at, trigger,
                    articles_discovered, articles_processed, articles_skipped, articles_failed,
                    entities_created, entities_updated, events_created, relationships_created,
                    error_details, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    completed_at = excluded.completed_at,
                    articles_discovered = excluded.articles_discovered,
                    articles_processed = excluded.articles_processed,
                    articles_skipped = excluded.articles_skipped,
                    articles_failed = excluded.articles_failed,
                    entities_created = excluded.entities_created,
                    entities_updated = excluded.entities_updated,
                    events_created = excluded.events_created,
                    relationships_created = excluded.relationships_created,
                    error_details = excluded.error_details,
                    metadata = excluded.metadata
                """,
                (
                    job.id,
                    job.job_type,
                    job.status,
                    job.started_at,
                    job.completed_at,
                    job.trigger,
                    job.articles_discovered,
                    job.articles_processed,
                    job.articles_skipped,
                    job.articles_failed,
                    job.entities_created,
                    job.entities_updated,
                    job.events_created,
                    job.relationships_created,
                    job.error_details,
                    json.dumps(job.metadata),
                ),
            )
            conn.commit()

    @staticmethod
    def list_jobs(limit: int = 20) -> list[dict]:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM ingestion_jobs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            res = []
            for r in rows:
                d = dict(r)
                d["metadata"] = json.loads(d.get("metadata") or "{}")
                res.append(d)
            return res
