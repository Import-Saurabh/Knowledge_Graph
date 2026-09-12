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