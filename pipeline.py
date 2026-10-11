"""
News → Knowledge Graph pipeline.

Fetches headlines from RSS feeds, sends them to Claude to extract entities
and relationships, then writes a graph.json file for the D3 visualiser.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python pipeline.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import boto3
import feedparser
from anthropic import Anthropic

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Anthropic / MiniMax config
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic")
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("MINIMAX_API_KEY")
LLM_MODEL          = os.environ.get("LLM_MODEL", "MiniMax-M3")

S3_BUCKET       = os.environ.get("S3_BUCKET", "news-knowledge-graph")
S3_KEY          = "graph.json"
S3_LOGS_BUCKET  = "news-knowledge-graph-logs"
TRAFFIC_KEY     = "last-traffic.json"
IDLE_SKIP_HOURS = 3    # skip if no traffic within this window
MAX_STALE_HOURS = 8    # always refresh if graph is older than this
SNS_TOPIC_ARN   = "arn:aws:sns:us-east-1:597062269817:graph-pipeline-alerts"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

RSS_FEEDS = [
    "http://feeds.bbci.co.uk/news/world/rss.xml",
    "https://feeds.npr.org/1001/rss.xml",
    "https://www.theguardian.com/world/rss",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://rss.dw.com/rdf/rss-en-world",
    "https://www.france24.com/en/rss",
]

MAX_ARTICLES_PER_FEED = 4  # sample evenly across feeds

# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_articles(max_per_feed: int = MAX_ARTICLES_PER_FEED) -> list[dict]:
    articles: list[dict] = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            count = 0
            for entry in feed.entries:
                if count >= max_per_feed:
                    break
                title = entry.get("title", "").strip()
                summary = entry.get("summary", "").strip()
                if title:
                    articles.append({
                        "title": title,
                        "summary": summary,
                        "link": entry.get("link", ""),
                    })
                    count += 1
            print(f"  {feed_url}: {len(feed.entries)} entries, took {count}")
        except Exception as exc:
            print(f"  Warning: could not fetch {feed_url}: {exc}", file=sys.stderr)
    return articles


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert geopolitical analyst building a knowledge graph from today's news.

Extract entities and relationships that reveal meaningful connections, cause-and-effect chains,
and patterns across world events. Prioritise entities that appear across multiple articles —
these are the high-influence nodes.

Entity types (use exactly these strings):