"""Unit tests for SQLite database layer, models, and graph queries."""
import os
import tempfile
import uuid
from pathlib import Path
import pytest

from server.config import settings
from server.database import GraphStore, init_db
from server.models import Article, Entity, Event, Relationship, Conversation, Message, utc_now_iso


@pytest.fixture(autouse=True)
def test_db():
    """Use a temporary database file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = Path(tf.name)
    
    orig_path = settings.db_path
    settings.db_path = db_path
    init_db(db_path)

    yield db_path

    settings.db_path = orig_path
    try:
        os.remove(db_path)
    except Exception:
        pass


def test_entity_crud_and_search():
    ent = Entity(
        id="test-saudi-arabia",
        entity_type="country",
        canonical_name="Kingdom of Saudi Arabia",
        description="Major Middle Eastern sovereign state.",
        aliases=["KSA", "Saudi"],
    )
    GraphStore.upsert_entity(ent)

    fetched = GraphStore.get_entity("test-saudi-arabia")
    assert fetched is not None
    assert fetched["canonical_name"] == "Kingdom of Saudi Arabia"
    assert "KSA" in fetched["aliases"]

    # FTS search
    results = GraphStore.search_entities("Saudi")
    assert len(results) >= 1
    assert any(r["id"] == "test-saudi-arabia" for r in results)


def test_event_crud():
    ev = Event(
        id="test-summit-2026",
        event_type="diplomatic_meeting",
        summary="High-level security summit in Riyadh.",
        event_time="2026-10-11",
        location="Riyadh",
    )