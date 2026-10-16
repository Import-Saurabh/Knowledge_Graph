"""Configuration management for DriftForge News Intelligence Platform."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseModel):
    # App & Server
    app_name: str = "DriftForge News Intelligence Platform"
    version: str = "2.0.0"
    host: str = Field(default_factory=lambda: os.environ.get("HOST", "0.0.0.0"))
    port: int = Field(default_factory=lambda: int(os.environ.get("PORT", "8080")))
    data_dir: Path = DATA_DIR

    # Database
    db_path: Path = Field(
        default_factory=lambda: Path(os.environ.get("DATABASE_PATH", str(DATA_DIR / "driftforge.db")))
    )
    kuzu_db_path: Path = Field(
        default_factory=lambda: Path(os.environ.get("KUZU_DB_PATH", str(DATA_DIR / "kuzu_store")))
    )
    use_kuzu: bool = Field(
        default_factory=lambda: os.environ.get("USE_KUZU", "true").lower() in ("true", "1", "yes")
    )

    # LLM Settings (MiniMax / Anthropic compatible)
    anthropic_base_url: str = Field(
        default_factory=lambda: os.environ.get("ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic")
    )
    anthropic_api_key: str = Field(
        default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("MINIMAX_API_KEY", "")
    )
    llm_model: str = Field(
        default_factory=lambda: os.environ.get("LLM_MODEL", "MiniMax-M3")
    )
    llm_timeout: int = Field(default_factory=lambda: int(os.environ.get("LLM_TIMEOUT", "60")))

    # Security & Auth
    admin_api_key: str = Field(
        default_factory=lambda: os.environ.get("ADMIN_API_KEY", "driftforge-admin-secret")
    )
    cors_origins: list[str] = ["*"]

    # Ingestion & Feeds (16+ Newsrooms)
    rss_feeds: list[str] = [
        "http://feeds.bbci.co.uk/news/world/rss.xml",
        "https://feeds.npr.org/1001/rss.xml",
        "https://www.theguardian.com/world/rss",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://rss.dw.com/rdf/rss-en-world",
        "https://www.france24.com/en/rss",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "https://www.euronews.com/rss?level=theme&name=news",
        "https://www.themoscowtimes.com/rss/news",
        "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms",
        "https://www.businessinsider.com/rss",
        "https://www.tehrantimes.com/rss",
    ]
    gnews_monitored_domains: list[str] = [
        "washingtonpost.com",
        "reuters.com",
        "bloomberg.com",
        "globaltimes.cn",
    ]
    gnews_max_per_domain: int = Field(
        default_factory=lambda: int(os.environ.get("GNEWS_MAX_PER_DOMAIN", "10"))
    )
    max_articles_per_feed: int = Field(
        default_factory=lambda: int(os.environ.get("MAX_ARTICLES_PER_FEED", "30"))
    )

    # Low-Latency Performance Settings
    feed_timeout_seconds: float = Field(
        default_factory=lambda: float(os.environ.get("FEED_TIMEOUT_SECONDS", "4.0"))
    )
    scrape_timeout_seconds: float = Field(
        default_factory=lambda: float(os.environ.get("SCRAPE_TIMEOUT_SECONDS", "3.5"))
    )
    max_scrape_workers: int = Field(
        default_factory=lambda: int(os.environ.get("MAX_SCRAPE_WORKERS", "10"))
    )
    max_article_text_chars: int = Field(
        default_factory=lambda: int(os.environ.get("MAX_ARTICLE_TEXT_CHARS", "3500"))
    )
    extractor_batch_size: int = Field(
        default_factory=lambda: int(os.environ.get("EXTRACTOR_BATCH_SIZE", "5"))
    )
    extractor_max_concurrency: int = Field(
        default_factory=lambda: int(os.environ.get("EXTRACTOR_MAX_CONCURRENCY", "2"))
    )
    max_process_per_run: int = Field(
        default_factory=lambda: int(os.environ.get("MAX_PROCESS_PER_RUN", "10"))
    )

    # Scheduling
    ingestion_schedule_minutes: int = Field(
        default_factory=lambda: int(os.environ.get("INGESTION_SCHEDULE_MINUTES", "1"))
    )
    ingestion_schedule_hours: Optional[int] = Field(
        default_factory=lambda: int(os.environ.get("INGESTION_SCHEDULE_HOURS")) if os.environ.get("INGESTION_SCHEDULE_HOURS") else None
    )
    scheduler_enabled: bool = Field(
        default_factory=lambda: os.environ.get("SCHEDULER_ENABLED", "true").lower() in ("true", "1", "yes")
    )
    timezone: str = Field(
        default_factory=lambda: os.environ.get("TIMEZONE", "UTC")
    )

    # Research budgets
    research_max_subqueries: int = 3
    research_max_articles: int = 12
    research_timeout_seconds: int = 45


settings = Settings()
