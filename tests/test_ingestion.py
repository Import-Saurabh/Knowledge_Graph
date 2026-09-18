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