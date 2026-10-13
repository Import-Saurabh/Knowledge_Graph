"""Unit tests for ingestion components: URL normalization, entity resolution, and feeds."""
import pytest
from server.ingestion.resolver import EntityResolver, slugify
from server.ingestion.sources import detect_publisher, normalize_url


def test_slugify():
    assert slugify("Saudi Arabia") == "saudi-arabia"
    assert slugify("United Nations (UN)") == "united-nations-un"
    assert slugify("Houthi Movement / Ansar Allah") == "houthi-movement-ansar-allah"
    assert slugify("  Extra   Spaces  ") == "extra-spaces"


def test_normalize_url():
    raw_url = "https://www.theguardian.com/world/2026/oct/11/news-story?utm_source=twitter&utm_medium=social&fbclid=123#comments"
    clean = normalize_url(raw_url)
    assert "utm_source" not in clean
    assert "fbclid" not in clean
    assert "#comments" not in clean
    assert clean == "https://www.theguardian.com/world/2026/oct/11/news-story"


def test_detect_publisher():
    assert detect_publisher("http://feeds.bbci.co.uk/news/world/rss.xml") == "BBC News"
    assert detect_publisher("https://www.theguardian.com/world/rss") == "The Guardian"
    assert detect_publisher("https://www.aljazeera.com/xml/rss/all.xml") == "Al Jazeera"
    assert detect_publisher("https://feeds.npr.org/1001/rss.xml") == "NPR"


def test_entity_resolver_aliases():
    aliases = ["UN", "United Nations"]
    new_aliases = EntityResolver.merge_aliases(aliases, "U.N.")
    assert "U.N." in new_aliases
    assert len(new_aliases) == 3

    # Duplicate should not be re-added
    same_aliases = EntityResolver.merge_aliases(new_aliases, "UN")
    assert len(same_aliases) == 3


def test_parse_entry_timestamp():
    from datetime import datetime, timezone
    import time
    from server.ingestion.sources import parse_entry_timestamp

    # 1. Test parsing from RFC 822 GMT string
    entry_rfc = {"published": "Mon, 12 Oct 2026 17:32:13 GMT"}
    ts = parse_entry_timestamp(entry_rfc)
    assert ts.startswith("2026-10-12T17:32:13")

    # 2. Test parsing from struct_time
    st = time.struct_time((2026, 10, 12, 18, 0, 0, 0, 285, 0))
    entry_struct = {"published_parsed": st}
    ts_struct = parse_entry_timestamp(entry_struct)
    assert ts_struct.startswith("2026-10-12T18:00:00")

    # 3. Test fallback to current timestamp when missing
    entry_empty = {}
    ts_now = parse_entry_timestamp(entry_empty)
    dt_now = datetime.fromisoformat(ts_now)
    now_utc = datetime.now(timezone.utc)
    diff = abs((now_utc - dt_now).total_seconds())
    assert diff < 5  # Created within the last 5 seconds
