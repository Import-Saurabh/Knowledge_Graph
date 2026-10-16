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
            new_articles = []
            for art in all_articles:
                if force or not GraphStore.article_exists_by_url(art.url):
                    new_articles.append(art)
                else:
                    job.articles_skipped += 1

            print(f"[Pipeline] Discovered: {job.articles_discovered}, Already stored: {job.articles_skipped}, New to process: {len(new_articles)}")

            if not new_articles:
                job.status = "completed"
                job.completed_at = utc_now_iso()
                GraphStore.record_job(job)
                GraphWriter.export_graph_snapshot()
                print("[Pipeline] No new articles to process. Job completed (snapshot refreshed).")
                return job

            # Pace processing per cycle (e.g. 10 articles) so each run finishes in ~5s without 429 rate limit errors
            max_process = getattr(settings, "max_process_per_run", 10)
            if len(new_articles) > max_process:
                print(f"[Pipeline] Pacing: processing top {max_process} of {len(new_articles)} new articles in this cycle...")
                new_articles = new_articles[:max_process]

            # 3. Scrape full text concurrently for new articles (ultra-low-latency 10-thread pool)
            from server.ingestion.sources import scrape_articles_parallel
            print(f"[Pipeline] Scraping full article bodies for {len(new_articles)} new articles concurrently...")
            new_articles = scrape_articles_parallel(
                new_articles,
                max_workers=getattr(settings, "max_scrape_workers", 10),
                timeout=getattr(settings, "scrape_timeout_seconds", 3.5),
                max_chars=getattr(settings, "max_article_text_chars", 3500),
            )

            # 4. Extract knowledge graph using LLM (parallel chunked batches)
            extracted = self.extractor.extract(new_articles)

            # 5. Persist extraction transactionally
            stats = self.writer.persist_extraction(new_articles, extracted)

            job.articles_processed = len(new_articles)
            job.entities_created = stats.get("entities_created", 0)
            job.entities_updated = stats.get("entities_updated", 0)
            job.events_created = stats.get("events_created", 0)
            job.relationships_created = stats.get("relationships_created", 0)
            job.status = "completed"
            job.completed_at = utc_now_iso()

            GraphStore.record_job(job)
            print(f"[Pipeline] Job {job_id} completed successfully: {stats}")
            return job

        except Exception as e:
            job.status = "failed"
            job.completed_at = utc_now_iso()
            job.error_details = str(e)
            GraphStore.record_job(job)
            print(f"[Pipeline] Job {job_id} failed: {e}", file=sys.stderr)
            raise
