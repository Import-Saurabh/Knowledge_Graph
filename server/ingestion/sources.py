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


def parse_entry_timestamp(entry: dict) -> str:
    """Parse RSS entry publication date into ISO 8601 UTC timestamp, defaulting to current time."""
    import calendar
    from datetime import datetime, timezone

    # 1. Check parsed struct_time provided by feedparser
    parsed_time = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed_time:
        try:
            secs = calendar.timegm(parsed_time)
            return datetime.fromtimestamp(secs, tz=timezone.utc).isoformat()
        except Exception:
            pass

    # 2. Try parsing raw RFC 822 / 2822 / ISO strings
    raw_str = entry.get("published") or entry.get("updated")
    if raw_str and isinstance(raw_str, str):
        try:
            import email.utils
            dt = email.utils.parsedate_to_datetime(raw_str)
            if dt:
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            pass
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(raw_str.replace("Z", "+00:00"))
            return dt.isoformat()
        except Exception:
            pass

    # 3. Default to current UTC timestamp so ingested news has real-time timestamp
    return utc_now_iso()


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
    if "nytimes." in domain:
        return "The New York Times"
    if "washingtonpost." in domain:
        return "The Washington Post"
    if "reuters." in domain:
        return "Reuters"
    if "euronews." in domain:
        return "Euronews"
    if "themoscowtimes." in domain:
        return "The Moscow Times"
    if "bloomberg." in domain:
        return "Bloomberg"
    if "globaltimes." in domain:
        return "Global Times"
    if "timesofindia." in domain or "indiatimes." in domain:
        return "The Times of India"
    if "businessinsider." in domain:
        return "Business Insider"
    if "tehrantimes." in domain:
        return "Tehran Times"
    return default or domain


def scrape_article_body(
    url: str,
    fallback_summary: str = "",
    timeout: float = 3.5,
    max_chars: int = 3500,
) -> str:
    """Scrape full article text using newspaper4k with strict timeout and fallback."""
    if not url:
        return fallback_summary
    try:
        import newspaper
        config = newspaper.Config()
        config.request_timeout = timeout
        config.fetch_images = False
        config.memoize_articles = False
        config.browser_user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        art = newspaper.article(url, config=config)
        text = (art.text or "").strip()
        if text and len(text) > 100:
            return text[:max_chars]
    except Exception:
        pass
    return fallback_summary


def scrape_articles_parallel(
    articles: list[Article],
    max_workers: int = 10,
    timeout: float = 3.5,
    max_chars: int = 3500,
) -> list[Article]:
    """Scrape full text concurrently across a batch of articles with strict deadline isolation."""
    if not articles:
        return []
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _worker(art: Article) -> Article:
        try:
            body = scrape_article_body(
                art.url,
                fallback_summary=art.summary or art.content_excerpt or art.headline,
                timeout=timeout,
                max_chars=max_chars,
            )
            if body:
                art.content_excerpt = body
                art.content_hash = compute_sha256(f"{art.headline}\n{body}")
        except Exception:
            pass
        return art

    workers = min(len(articles), max_workers)
    result_map = {a.id: a for a in articles}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        f_to_id = {executor.submit(_worker, a): a.id for a in articles}
        try:
            for fut in as_completed(f_to_id, timeout=timeout + 2.0):
                try:
                    res_art = fut.result()
                    result_map[res_art.id] = res_art
                except Exception:
                    pass
        except Exception:
            pass
    return [result_map[a.id] for a in articles]


def discover_gnews_articles(
    domains: Optional[list[str]] = None,
    max_per_domain: int = 10,
) -> list[Article]:
    """Discover recent articles from domains via GNews concurrently."""
    target_domains = domains or settings.gnews_monitored_domains
    if not target_domains:
        return []
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from gnews import GNews

    def _fetch_domain(domain: str) -> list[Article]:
        domain_articles = []
        try:
            gn = GNews(language="en", period="2d", max_results=max_per_domain)
            items = gn.get_news_by_site(domain)
            pub_name = detect_publisher(f"https://{domain}")
            for item in items:
                raw_url = item.get("url", "")
                title = item.get("title", "").strip()
                summary = item.get("description", "").strip()
                pub_date = item.get("published date", "")
                if not raw_url or not title:
                    continue
                clean_url = normalize_url(raw_url)
                url_hash = compute_sha256(clean_url)
                domain_articles.append(Article(
                    id=str(uuid.uuid4()),
                    url=clean_url,
                    url_hash=url_hash,
                    publisher=pub_name,
                    headline=title,
                    summary=summary,
                    content_excerpt=summary[:500] if summary else title,
                    content_hash=compute_sha256(f"{title}\n{summary}"),
                    published_at=pub_date or utc_now_iso(),
                    ingested_at=utc_now_iso(),
                    feed_source=f"gnews:{domain}",
                    extraction_status="pending",
                    metadata={"source_domain": domain},
                ))
        except Exception as exc:
            print(f"[GNews] Error fetching from {domain}: {exc}", file=sys.stderr)
        return domain_articles

    discovered = []
    with ThreadPoolExecutor(max_workers=min(len(target_domains), 8)) as executor:
        futures = [executor.submit(_fetch_domain, d) for d in target_domains]
        for fut in as_completed(futures):
            try:
                discovered.extend(fut.result())
            except Exception as e:
                print(f"[GNews] Worker error: {e}", file=sys.stderr)
    return discovered


class RSSConnector:
    """Connector for discovering and fetching articles from RSS and Atom feeds."""

    def __init__(self, feeds: Optional[list[str]] = None):
        self.feeds = feeds or settings.rss_feeds

    def _fetch_single_feed(self, feed_url: str, max_per_feed: int) -> list[Article]:
        items = []
        try:
            import urllib.request
            req = urllib.request.Request(
                feed_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            with urllib.request.urlopen(req, timeout=settings.feed_timeout_seconds) as response:
                xml_data = response.read()
            feed = feedparser.parse(xml_data)
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

                published_at = parse_entry_timestamp(entry)

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

    def discover_articles(self, max_per_feed: Optional[int] = None) -> list[Article]:
        """Fetch articles concurrently across all RSS feeds and GNews domains with per-source error isolation."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        limit = max_per_feed or settings.max_articles_per_feed
        discovered: list[Article] = []

        # 1. Fetch direct RSS feeds concurrently
        with ThreadPoolExecutor(max_workers=min(len(self.feeds), 16)) as executor:
            futures = [executor.submit(self._fetch_single_feed, url, limit) for url in self.feeds]
            for fut in as_completed(futures):
                try:
                    discovered.extend(fut.result())
                except Exception as exc:
                    print(f"[RSSConnector] Thread execution error: {exc}", file=sys.stderr)

        # 2. Fetch GNews monitored domains concurrently
        if getattr(settings, "gnews_monitored_domains", None):
            try:
                gnews_items = discover_gnews_articles(
                    domains=settings.gnews_monitored_domains,
                    max_per_domain=settings.gnews_max_per_domain,
                )
                discovered.extend(gnews_items)
            except Exception as exc:
                print(f"[RSSConnector] GNews discovery error: {exc}", file=sys.stderr)

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
                published_at = parse_entry_timestamp(entry)

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
