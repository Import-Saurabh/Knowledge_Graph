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
    GraphStore.upsert_event(ev)

    fetched = GraphStore.get_event("test-summit-2026")
    assert fetched is not None
    assert fetched["summary"] == "High-level security summit in Riyadh."
    assert fetched["location"] == "Riyadh"


def test_relationship_and_subgraph():
    ent1 = Entity(id="node-a", entity_type="country", canonical_name="Node A")
    ent2 = Entity(id="node-b", entity_type="country", canonical_name="Node B")
    ent3 = Entity(id="node-c", entity_type="country", canonical_name="Node C")
    GraphStore.upsert_entity(ent1)
    GraphStore.upsert_entity(ent2)
    GraphStore.upsert_entity(ent3)

    rel1 = Relationship(
        id="rel-1",
        source_id="node-a",
        target_id="node-b",
        relationship_type="ALLIES_WITH",
        description="Mutual alliance",
    )
    rel2 = Relationship(
        id="rel-2",
        source_id="node-b",
        target_id="node-c",
        relationship_type="TRADE_WITH",
        description="Economic partnership",
    )
    GraphStore.upsert_relationship(rel1)
    GraphStore.upsert_relationship(rel2)

    rels = GraphStore.get_relationships_for_entity("node-b")
    assert len(rels) == 2

    # Subgraph multi-hop
    subgraph = GraphStore.get_subgraph(["node-a"], max_hops=2)
    sub_node_ids = {n["id"] for n in subgraph["nodes"]}
    assert "node-a" in sub_node_ids
    assert "node-b" in sub_node_ids
    assert "node-c" in sub_node_ids


def test_article_deduplication():
    art1 = Article(
        id=str(uuid.uuid4()),
        url="https://www.bbc.com/news/world-12345?utm_source=rss",
        url_hash="hash1",
        headline="Breaking News Test",
    )
    is_new = GraphStore.upsert_article(art1)
    assert is_new is True

    # Same URL should not be inserted again
    art2 = Article(
        id=str(uuid.uuid4()),
        url="https://www.bbc.com/news/world-12345?utm_source=rss",
        url_hash="hash1",
        headline="Breaking News Test (Duplicate)",
    )
    is_duplicate = GraphStore.upsert_article(art2)
    assert is_duplicate is False


def test_conversations_and_messages():
    conv_id = "test-conv-123"
    GraphStore.create_conversation(conv_id, title="Test Chat")

    msg = Message(
        id="msg-1",
        conversation_id=conv_id,
        role="user",
        content="What is happening in the Middle East?",
    )
    GraphStore.save_message(msg)

    conv = GraphStore.get_conversation(conv_id)
    assert conv is not None
    assert conv["title"] == "Test Chat"
    assert len(conv["messages"]) == 1
    assert conv["messages"][0]["content"] == "What is happening in the Middle East?"
