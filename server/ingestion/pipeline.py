"""Main ingestion pipeline orchestrator."""
from __future__ import annotations

import sys
import uuid
from typing import Optional

from server.config import settings
from server.database import GraphStore
from server.ingestion.extractor import LLMExtractor
from server.ingestion.sources import RSSConnector
from server.ingestion.writer import GraphWriter
from server.models import IngestionJob, utc_now_iso


class IngestionPipeline:
    """Orchestrates news discovery, deduplication, LLM extraction, and persistent storage."""

    def __init__(self):
        self.sources = RSSConnector()
        self.extractor = LLMExtractor()
        self.writer = GraphWriter()

    def run(
        self,
        trigger: str = "scheduler",
        max_per_feed: Optional[int] = None,
        force: bool = False,
    ) -> IngestionJob:
        job_id = str(uuid.uuid4())
        started_at = utc_now_iso()

        job = IngestionJob(
            id=job_id,
            job_type="scheduled" if "scheduler" in trigger else "manual",
            status="running",
            started_at=started_at,
            trigger=trigger,
        )
        GraphStore.record_job(job)

        try:
            limit = max_per_feed or settings.max_articles_per_feed
            print(f"[Pipeline] Starting ingestion job {job_id} (trigger: {trigger}, max_per_feed: {limit})")

            # 1. Discover candidate articles across RSS feeds
            all_articles = self.sources.discover_articles(max_per_feed=limit)
            job.articles_discovered = len(all_articles)

            # 2. Filter out already processed articles