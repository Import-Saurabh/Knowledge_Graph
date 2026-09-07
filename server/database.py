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