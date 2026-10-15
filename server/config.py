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

    # Ingestion & Feeds
    rss_feeds: list[str] = [
        "http://feeds.bbci.co.uk/news/world/rss.xml",
        "https://feeds.npr.org/1001/rss.xml",
        "https://www.theguardian.com/world/rss",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://rss.dw.com/rdf/rss-en-world",
        "https://www.france24.com/en/rss",
    ]
    max_articles_per_feed: int = Field(
        default_factory=lambda: int(os.environ.get("MAX_ARTICLES_PER_FEED", "4"))
    )

    # Scheduling
    ingestion_schedule_minutes: int = Field(
        default_factory=lambda: int(os.environ.get("INGESTION_SCHEDULE_MINUTES", "2"))
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
