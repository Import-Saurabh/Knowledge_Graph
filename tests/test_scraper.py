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


def test_newspaper_installed_and_scrapes_text(monkeypatch):
    """Gap in tests fix (Point 12): verify newspaper4k is installed and parses article text."""
    import newspaper
    assert hasattr(newspaper, "article")

    class MockArticle:
        text = "This is a detailed international news article discussing global diplomacy and economic developments across multiple regions in 2026."

    monkeypatch.setattr(newspaper, "article", lambda *args, **kwargs: MockArticle())

    scraped = scrape_article_body("https://test-outlet.com/story", fallback_summary="Fallback", timeout=2.0)
    assert "diplomacy" in scraped
    assert scraped != "Fallback"


def test_gnews_date_parsing_iso():
    """Bug #11 & Point 12: test that GNews dates are converted to ISO 8601 format."""
    from server.ingestion.sources import _parse_gnews_date

    # RFC 822 format typical in Google News feeds
    rfc_date = "Fri, 16 Oct 2026 14:30:00 GMT"
    iso_result = _parse_gnews_date(rfc_date)
    assert iso_result.startswith("2026-10-16T14:30:00")

    # Already ISO format
    already_iso = "2026-10-16T14:30:00+00:00"
    assert _parse_gnews_date(already_iso).startswith("2026-10-16")

    # None or empty fallback
    assert _parse_gnews_date("") is not None


def test_gnews_redirect_resolution(monkeypatch):
    """Bug #2 & Point 12: test resolving Google redirect URLs to actual publisher URLs."""
    from server.ingestion.sources import _resolve_gnews_url

    # Non-redirect URL should pass through untouched without network call
    direct_url = "https://www.reuters.com/world/news-item"
    assert _resolve_gnews_url(direct_url) == direct_url

    # Google redirect URL resolved via mock
    class MockResponse:
        url = "https://www.bloomberg.com/news/articles/2026-10-16/actual-story"
        def __enter__(self): return self
        def __exit__(self, *args): pass

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: MockResponse())

    resolved = _resolve_gnews_url("https://news.google.com/rss/articles/CBMi12345")
    assert resolved == "https://www.bloomberg.com/news/articles/2026-10-16/actual-story"


def test_discover_gnews_articles_mocked(monkeypatch):
    """Point 12: test GNews discovery without making real network calls."""
    class MockGNews:
        def __init__(self, **kwargs): pass
        def get_news_by_site(self, domain):
            return [
                {
                    "title": "Global Trade Summit Concludes",
                    "description": "Delegates reached agreement on cross-border logistics.",
                    "url": f"https://{domain}/story-1",
                    "published date": "Fri, 16 Oct 2026 10:00:00 GMT",
                }
            ]

    import gnews
    monkeypatch.setattr(gnews, "GNews", MockGNews)

    articles = discover_gnews_articles(domains=["reuters.com"], max_per_domain=5)
    assert len(articles) == 1
    art = articles[0]
    assert art.publisher == "Reuters"
    assert art.headline == "Global Trade Summit Concludes"
    assert art.feed_source == "gnews:reuters.com"
    assert "2026-10-16" in str(art.published_at)


def test_discover_articles_interleaving(monkeypatch):
    """Bug #2 & Point 12: test that discover_articles interleaves RSS and GNews articles."""
    from server.ingestion.sources import RSSConnector

    connector = RSSConnector(feeds=["https://feed1.com/rss"])

    def mock_fetch_feed(url, limit):
        return [
            Article(
                id="rss-1",
                url="https://feed1.com/art1",
                url_hash="h1",
                headline="RSS Art 1",
                published_at=utc_now_iso(),
                ingested_at=utc_now_iso(),
            ),
            Article(
                id="rss-2",
                url="https://feed1.com/art2",
                url_hash="h2",
                headline="RSS Art 2",
                published_at=utc_now_iso(),
                ingested_at=utc_now_iso(),
            ),
        ]

    def mock_discover_gnews(domains, max_per_domain):
        return [
            Article(
                id="gnews-1",
                url="https://gnews.com/art1",
                url_hash="gh1",
                headline="GNews Art 1",
                published_at=utc_now_iso(),
                ingested_at=utc_now_iso(),
            )
        ]

    monkeypatch.setattr(connector, "_fetch_single_feed", mock_fetch_feed)
    monkeypatch.setattr("server.ingestion.sources.discover_gnews_articles", mock_discover_gnews)

    discovered = connector.discover_articles()
    # Interleaved order should have GNews article between or alternating with RSS articles
    urls = [a.url for a in discovered]
    assert "https://feed1.com/art1" in urls
    assert "https://gnews.com/art1" in urls
    # First should be RSS, second should be GNews
    assert urls[0] == "https://feed1.com/art1"
    assert urls[1] == "https://gnews.com/art1"
    assert urls[2] == "https://feed1.com/art2"


def test_batch_extraction_and_merging(monkeypatch):
    """Point 12: test multi-chunk extraction and entity deduplication across batches."""
    from server.config import settings
    extractor = LLMExtractor()

    call_count = 0
    def mock_extract_chunk(chunk, offset):
        nonlocal call_count
        call_count += 1
        if offset == 0:
            return {
                "entities": [{"id": "shared-entity", "label": "Shared"}, {"id": "chunk-1-ent", "label": "E1"}],
                "events": [{"id": "ev-1", "article_index": 1}],
                "relationships": [{"source": "shared-entity", "target": "chunk-1-ent", "article_index": 1}],
                "claims": [{"claim_text": "Claim 1", "article_index": 1}],
            }
        else:
            return {
                "entities": [{"id": "shared-entity", "label": "Shared (Dup)"}, {"id": "chunk-2-ent", "label": "E2"}],
                "events": [{"id": "ev-2", "article_index": 3}],
                "relationships": [{"source": "shared-entity", "target": "chunk-2-ent", "article_index": 3}],
                "claims": [{"claim_text": "Claim 2", "article_index": 3}],
            }

    monkeypatch.setattr(extractor, "_extract_chunk", mock_extract_chunk)
    monkeypatch.setattr(settings, "extractor_batch_size", 2)
    monkeypatch.setattr(settings, "extractor_max_concurrency", 2)

    articles = [
        Article(id=f"a{i}", url=f"https://test.com/{i}", url_hash=f"h{i}", headline=f"H{i}")
        for i in range(4)
    ]

    result = extractor.extract(articles)
    assert call_count == 2
    # Shared entity should be deduplicated
    entity_ids = [e["id"] for e in result["entities"]]
    assert entity_ids.count("shared-entity") == 1
    assert "chunk-1-ent" in entity_ids
    assert "chunk-2-ent" in entity_ids
    assert len(result["events"]) == 2
    assert len(result["relationships"]) == 2
    assert len(result["claims"]) == 2


def test_non_number_article_index_handled(monkeypatch):
    """Bug #7 fix: a non-number article_index should not crash the batch."""
    extractor = LLMExtractor()

    class MockContent:
        text = '{"entities": [], "events": [{"id": "ev1", "article_index": "not-a-number"}], "relationships": [{"source": "a", "target": "b", "article_index": null}], "claims": []}'

    class MockResponse:
        content = [MockContent()]

    class MockMessages:
        @staticmethod
        def create(*args, **kwargs):
            return MockResponse()

    monkeypatch.setattr(extractor.client, "messages", MockMessages())

    art = Article(id="1", url="https://test.com/1", url_hash="h1", headline="H1")
    # Should not raise TypeError / ValueError
    res = extractor._extract_chunk([art], offset=2)
    assert res["events"][0]["article_index"] == 3  # default 1 + offset 2 = 3


def test_thinking_block_handling(monkeypatch):
    """Bug #13 fix: extraction should handle LLMs that reply with a thinking block first."""
    extractor = LLMExtractor()

    class MockThinkingBlock:
        type = "thinking"
        thinking = "Here is my internal chain of thought about geopolitics..."

    class MockTextBlock:
        type = "text"
        text = '{"entities": [{"id": "minimax-actor", "label": "MiniMax Actor"}], "events": [], "relationships": [], "claims": []}'

    class MockResponse:
        content = [MockThinkingBlock(), MockTextBlock()]

    class MockMessages:
        @staticmethod
        def create(*args, **kwargs):
            return MockResponse()

    monkeypatch.setattr(extractor.client, "messages", MockMessages())

    art = Article(id="1", url="https://test.com/1", url_hash="h1", headline="H1")
    res = extractor._extract_chunk([art], offset=0)
    assert len(res["entities"]) == 1
    assert res["entities"][0]["id"] == "minimax-actor"
