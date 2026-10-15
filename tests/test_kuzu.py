"""Tests for Kùzu embedded graph engine, compact triple serialization, and KV caching context formatting."""
import shutil
import tempfile
from pathlib import Path
import pytest

from server.kuzu_store import KuzuGraphEngine
from server.query.synthesizer import format_compact_triples, format_deduplicated_sources


@pytest.fixture
def kuzu_temp_engine():
    """Create a temporary Kùzu database instance for isolated tests."""
    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / "test_kuzu_engine"
    KuzuGraphEngine.reset(db_path)
    yield KuzuGraphEngine
    shutil.rmtree(temp_dir, ignore_errors=True)
    KuzuGraphEngine.reset()


def test_kuzu_entity_and_relationship_crud(kuzu_temp_engine):
    # Upsert entities
    kuzu_temp_engine.upsert_entity(
        entity_id="iran",
        canonical_name="Islamic Republic of Iran",
        entity_type="country",
        description="Middle Eastern nation",
    )
    kuzu_temp_engine.upsert_entity(
        entity_id="iaea",
        canonical_name="International Atomic Energy Agency",
        entity_type="organization",
        description="UN nuclear watchdog",
    )

    # Upsert relationship
    kuzu_temp_engine.upsert_relationship(
        source_id="iaea",
        target_id="iran",
        relationship_type="INSPECTED",
        description="Conducted nuclear safeguard inspections",
    )

    # Multi-hop retrieval
    subgraph = kuzu_temp_engine.get_subgraph(["iaea"], max_hops=1)
    nodes = {n["id"]: n for n in subgraph["nodes"]}
    assert "iaea" in nodes
    assert "iran" in nodes
    assert nodes["iaea"]["label"] == "International Atomic Energy Agency"
    assert nodes["iran"]["type"] == "country"

    links = subgraph["links"]
    assert len(links) >= 1
    assert any(l["source"] == "iaea" and l["target"] == "iran" and l["type"] == "INSPECTED" for l in links)


def test_kuzu_multi_hop_chain(kuzu_temp_engine):
    # Chain: A -> B -> C
    kuzu_temp_engine.upsert_entity("alpha", "Alpha Nation", "country")
    kuzu_temp_engine.upsert_entity("beta", "Beta Org", "organization")
    kuzu_temp_engine.upsert_entity("gamma", "Gamma Facility", "facility")

    kuzu_temp_engine.upsert_relationship("alpha", "beta", "FUNDS", "Direct funding")
    kuzu_temp_engine.upsert_relationship("beta", "gamma", "OPERATES", "Facility operations")

    # 1 hop from alpha should find beta, but not gamma
    subgraph_1 = kuzu_temp_engine.get_subgraph(["alpha"], max_hops=1)
    nids_1 = {n["id"] for n in subgraph_1["nodes"]}
    assert "alpha" in nids_1
    assert "beta" in nids_1
    assert "gamma" not in nids_1

    # 2 hops from alpha should reach gamma
    subgraph_2 = kuzu_temp_engine.get_subgraph(["alpha"], max_hops=2)
    nids_2 = {n["id"] for n in subgraph_2["nodes"]}
    assert "alpha" in nids_2
    assert "beta" in nids_2
    assert "gamma" in nids_2


def test_format_compact_triples():
    entities = [
        {"id": "usa", "canonical_name": "United States", "entity_type": "country", "description": "Global power"},
        {"id": "japan", "canonical_name": "Japan", "entity_type": "country", "description": "East Asian ally"},
    ]
    subgraph = {
        "links": [
            {
                "source": "usa",
                "target": "japan",
                "type": "TREATY_ALLY",
                "description": "Mutual defense treaty",
            }
        ]
    }

    ent_text, rel_text = format_compact_triples(subgraph, entities)

    # Check linearized triple format: [Subject] -[:REL]-> [Object] | desc
    assert "[United States] -[:TREATY_ALLY]-> [Japan] | Mutual defense treaty" in rel_text
    # Check compact entity listing
    assert "- [usa] United States (country): Global power" in ent_text
    assert "- [japan] Japan (country): East Asian ally" in ent_text


def test_format_deduplicated_sources():
    articles = [
        {
            "id": "art-1",
            "publisher": "Reuters",
            "headline": "Historic Treaty Signed",
            "published_at": "2026-10-14",
            "url": "https://reuters.com/news/123",
            "summary": "This is a very long article summary that should be omitted when covered in claims...",
        },
        {
            "id": "art-2",
            "publisher": "BBC",
            "headline": "Economic Impact Discussed",
            "published_at": "2026-10-14",
            "url": "https://bbc.com/news/456",
            "summary": "Economic analysis details...",
        },
    ]

    claims = [
        {
            "claim_text": "Treaty formally ratified by senate.",
            "attribution": "government",
            "headline": "Historic Treaty Signed",
            "source_article_id": "art-1",
        }
    ]

    claims_text, arts_text = format_deduplicated_sources(articles, claims)

    # art-1 is covered in claims, so long excerpt should be skipped
    assert "[Captured in claims]" in arts_text
    assert "This is a very long article summary" not in arts_text

    # art-2 is not in claims, so key excerpt is kept concisely
    assert "Key excerpt: Economic analysis details" in arts_text
