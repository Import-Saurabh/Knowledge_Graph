"""Unit and integration tests for expanded newsroom discovery, newspaper4k scraping, GNews, and batching."""
import pytest
import uuid

from server.models import Article, utc_now_iso
from server.ingestion.sources import (
    detect_publisher,
    scrape_article_body,
    scrape_articles_parallel,
    discover_gnews_articles,
)
from server.ingestion.extractor import LLMExtractor


def test_publisher_detection_all_16_newsrooms():
    test_cases = [
        ("https://www.bbc.com/news/world-123", "BBC News"),
        ("https://feeds.npr.org/1001/rss.xml", "NPR"),
        ("https://www.theguardian.com/world/2026/oct/16/story", "The Guardian"),
        ("https://www.aljazeera.com/news/2026/10/16/report", "Al Jazeera"),
        ("https://www.dw.com/en/world-affairs/a-12345", "Deutsche Welle"),
        ("https://www.france24.com/en/americas/story", "France 24"),
        ("https://www.nytimes.com/2026/10/16/world/middleeast/update.html", "The New York Times"),
        ("https://www.washingtonpost.com/world/2026/10/16/analysis", "The Washington Post"),
        ("https://www.reuters.com/world/europe/ukraine-report-2026", "Reuters"),
        ("https://www.euronews.com/2026/10/16/eu-diplomacy-talks", "Euronews"),
        ("https://www.themoscowtimes.com/2026/10/16/kremlin-briefing-a123", "The Moscow Times"),
        ("https://www.bloomberg.com/news/articles/2026-10-16/fed-update", "Bloomberg"),
        ("https://www.globaltimes.cn/page/202610/123456.shtml", "Global Times"),
        ("https://timesofindia.indiatimes.com/world/rest-of-world/story/123.cms", "The Times of India"),
        ("https://www.businessinsider.com/tech-economy-brief-2026", "Business Insider"),
        ("https://www.tehrantimes.com/news/12345/diplomatic-ties", "Tehran Times"),
    ]
    for url, expected_publisher in test_cases:
        detected = detect_publisher(url)
        assert detected == expected_publisher, f"Failed for {url}: got {detected}, expected {expected_publisher}"


def test_scrape_article_body_with_fallback():
    # Invalid / unreachable URL should return fallback immediately
    fallback = "Summary fallback text"
    result = scrape_article_body("https://invalid-non-existent-domain-12345.com/page", fallback_summary=fallback, timeout=0.5)
    assert result == fallback

    # Empty URL returns fallback
    assert scrape_article_body("", fallback_summary=fallback) == fallback


def test_scrape_articles_parallel():
    art1 = Article(
        id=str(uuid.uuid4()),
        url="https://invalid-site-1.org/story1",
        url_hash="hash1",
        headline="Test Story 1",
        summary="Fallback summary 1",
        content_excerpt="Fallback summary 1",
        content_hash="chash1",
        published_at=utc_now_iso(),
        ingested_at=utc_now_iso(),
    )
    art2 = Article(
        id=str(uuid.uuid4()),
        url="https://invalid-site-2.org/story2",
        url_hash="hash2",
        headline="Test Story 2",
        summary="Fallback summary 2",
        content_excerpt="Fallback summary 2",
        content_hash="chash2",
        published_at=utc_now_iso(),
        ingested_at=utc_now_iso(),
    )

    scraped = scrape_articles_parallel([art1, art2], max_workers=2, timeout=0.5)
    assert len(scraped) == 2
    assert scraped[0].content_excerpt == "Fallback summary 1"
    assert scraped[1].content_excerpt == "Fallback summary 2"


def test_extractor_offset_remapping(monkeypatch):
    extractor = LLMExtractor()

    # Mock client.messages.create to test offset remapping logic without calling API
    class MockContent:
        text = '{"entities": [{"id": "e1"}], "events": [{"article_index": 1}], "relationships": [{"article_index": 1}], "claims": [{"article_index": 1}]}'

    class MockResponse:
        content = [MockContent()]

    class MockMessages:
        @staticmethod
        def create(*args, **kwargs):
            return MockResponse()

    monkeypatch.setattr(extractor.client, "messages", MockMessages())

    art = Article(
        id=str(uuid.uuid4()),
        url="https://test.com/1",
        url_hash="h1",
        headline="H1",
        published_at=utc_now_iso(),
        ingested_at=utc_now_iso(),
    )

    # Offset = 5 (e.g. 2nd batch starting at index 5)
    res = extractor._extract_chunk([art], offset=5)
    assert res["events"][0]["article_index"] == 6
    assert res["relationships"][0]["article_index"] == 6
    assert res["claims"][0]["article_index"] == 6
