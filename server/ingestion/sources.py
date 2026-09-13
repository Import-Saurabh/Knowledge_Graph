"""News source connectors for RSS feeds with URL normalization and deduplication."""
from __future__ import annotations

import hashlib
import sys
import uuid
from typing import Optional
from urllib.parse import urlparse, urlunparse

import feedparser

from server.config import settings
from server.models import Article, utc_now_iso


def normalize_url(url: str) -> str:
    """Normalize URL by stripping tracking queries and standardizing formatting."""
    parsed = urlparse(url.strip())
    # Strip tracking query params
    params_to_remove = {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "fbclid", "gclid", "ref", "ref_src", "source"
    }
    query_parts = []
    if parsed.query:
        for qp in parsed.query.split("&"):
            if "=" in qp:
                k, v = qp.split("=", 1)
                if k.lower() not in params_to_remove:
                    query_parts.append(qp)
            else:
                query_parts.append(qp)

    clean_query = "&".join(query_parts)
    clean_url = urlunparse((
        parsed.scheme.lower() or "https",
        parsed.netloc.lower(),
        parsed.path,
        parsed.params,
        clean_query,
        "",  # drop fragment
    ))
    return clean_url


def compute_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def detect_publisher(url: str, default: Optional[str] = None) -> str:
    domain = urlparse(url).netloc.lower()
    if "bbc." in domain or "bbci." in domain:
        return "BBC News"
    if "npr." in domain:
        return "NPR"
    if "theguardian." in domain:
        return "The Guardian"
    if "aljazeera." in domain:
        return "Al Jazeera"
    if "dw." in domain:
        return "Deutsche Welle"
    if "france24." in domain:
        return "France 24"
    return default or domain


class RSSConnector:
    """Connector for discovering and fetching articles from RSS and Atom feeds."""

    def __init__(self, feeds: Optional[list[str]] = None):
        self.feeds = feeds or settings.rss_feeds

    def _fetch_single_feed(self, feed_url: str, max_per_feed: int) -> list[Article]:
        items = []
        try:
            feed = feedparser.parse(feed_url)
            publisher = detect_publisher(feed_url, feed.feed.get("title", ""))
            count = 0

            for entry in feed.entries:
                if count >= max_per_feed:
                    break

                raw_link = entry.get("link", "").strip()
                title = entry.get("title", "").strip()
                summary = entry.get("summary", "").strip()

                if not raw_link or not title:
                    continue

                clean_url = normalize_url(raw_link)
                url_hash = compute_sha256(clean_url)
                content_str = f"{title}\n{summary}"
                content_hash = compute_sha256(content_str)

                published_at = entry.get("published", None) or entry.get("updated", None)

                article = Article(
                    id=str(uuid.uuid4()),
                    url=clean_url,
                    url_hash=url_hash,
                    publisher=publisher,
                    headline=title,
                    summary=summary,
                    content_excerpt=summary[:500] if summary else title,
                    content_hash=content_hash,
                    author=entry.get("author", None),
                    published_at=published_at,
                    ingested_at=utc_now_iso(),
                    feed_source=feed_url,
                    extraction_status="pending",
                    metadata={"feed_title": feed.feed.get("title", "")},
                )
                items.append(article)
                count += 1

            print(f"[RSSConnector] {feed_url}: {len(feed.entries)} entries found, collected {count}")
        except Exception as exc:
            print(f"[RSSConnector] Warning: could not parse feed {feed_url}: {exc}", file=sys.stderr)
        return items

    def discover_articles(self, max_per_feed: int = 4) -> list[Article]:
        """Fetch articles concurrently across feeds with per-source error isolation."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        discovered: list[Article] = []
        with ThreadPoolExecutor(max_workers=min(len(self.feeds), 6)) as executor:
            futures = [executor.submit(self._fetch_single_feed, url, max_per_feed) for url in self.feeds]
            for fut in as_completed(futures):
                try:
                    discovered.extend(fut.result())
                except Exception as exc:
                    print(f"[RSSConnector] Thread execution error: {exc}", file=sys.stderr)
        return discovered

    def search_topic_articles(self, query: str, max_articles: int = 6) -> list[Article]:
        """Search live wire news for a specific topic query via Google News RSS search."""
        import urllib.parse
        encoded_q = urllib.parse.quote_plus(query.strip())
        search_feed_url = f"https://news.google.com/rss/search?q={encoded_q}&hl=en-US&gl=US&ceid=US:en"

        articles: list[Article] = []
        try:
            feed = feedparser.parse(search_feed_url)
            for entry in feed.entries[:max_articles]:
                raw_link = entry.get("link", "").strip()
                title = entry.get("title", "").strip()
                summary = entry.get("summary", "").strip()
                if not raw_link or not title:
                    continue

                publisher = entry.get("source", {}).get("title")
                if not publisher and " - " in title:
                    publisher = title.rsplit(" - ", 1)[1].strip()
                if not publisher:
                    publisher = "Wire News"

                clean_title = title
                if " - " in title and publisher and clean_title.endswith(f" - {publisher}"):
                    clean_title = clean_title[:-(len(publisher) + 3)].strip()

                clean_url = normalize_url(raw_link)
                url_hash = compute_sha256(clean_url)
                content_str = f"{clean_title}\n{summary}"
                content_hash = compute_sha256(content_str)
                published_at = entry.get("published", None) or entry.get("updated", None)

                articles.append(Article(
                    id=str(uuid.uuid4()),
                    url=clean_url,
                    url_hash=url_hash,
                    publisher=publisher,
                    headline=clean_title,
                    summary=summary,
                    content_excerpt=summary[:500] if summary else clean_title,
                    content_hash=content_hash,
                    published_at=published_at,
                    ingested_at=utc_now_iso(),
                    feed_source=f"topic_search:{query}",
                    extraction_status="pending",
                    metadata={"topic_search": query},
                ))
            print(f"[RSSConnector] Topic search for '{query}': found {len(feed.entries)} entries, collected {len(articles)}")
        except Exception as exc:
            print(f"[RSSConnector] Topic search failed for '{query}': {exc}", file=sys.stderr)
        return articles
