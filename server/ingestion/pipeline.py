"""Main ingestion pipeline orchestrator."""
from __future__ import annotations

import logging
import sys
import uuid
from typing import Optional

from server.config import settings
from server.database import GraphStore
from server.ingestion.extractor import LLMExtractor
from server.ingestion.sources import RSSConnector
from server.ingestion.writer import GraphWriter
from server.models import IngestionJob, utc_now_iso

logger = logging.getLogger(__name__)


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
            logger.info(f"[Pipeline] Starting ingestion job {job_id} (trigger: {trigger}, max_per_feed: {limit})")

            # 1. Discover candidate articles across RSS feeds
            all_articles = self.sources.discover_articles(max_per_feed=limit)
            job.articles_discovered = len(all_articles)

            # 2. Filter out already processed articles (only skip if successfully extracted)
            # Bug #1 fix: failed articles are retried rather than lost forever
            new_articles = []
            for art in all_articles:
                if force or not GraphStore.article_extracted_by_url(art.url):
                    new_articles.append(art)
                else:
                    job.articles_skipped += 1

            logger.info(f"[Pipeline] Discovered: {job.articles_discovered}, Already stored: {job.articles_skipped}, New to process: {len(new_articles)}")

            if not new_articles:
                job.status = "completed"
                job.completed_at = utc_now_iso()
                GraphStore.record_job(job)
                GraphWriter.export_graph_snapshot()
                logger.info("[Pipeline] No new articles to process. Job completed (snapshot refreshed).")
                return job

            # Bug #4 fix: raise per-run cap from a hard 10 to a configurable
            # value, defaulting to 50, so more articles are processed before
            # they age off the feeds.
            max_process = getattr(settings, "max_process_per_run", 50)
            if len(new_articles) > max_process:
                logger.info(f"[Pipeline] Pacing: processing top {max_process} of {len(new_articles)} new articles in this cycle...")
                new_articles = new_articles[:max_process]

            # 3. Scrape full text concurrently for new articles (ultra-low-latency 10-thread pool)
            from server.ingestion.sources import scrape_articles_parallel
            logger.info(f"[Pipeline] Scraping full article bodies for {len(new_articles)} new articles concurrently...")
            new_articles = scrape_articles_parallel(
                new_articles,
                max_workers=getattr(settings, "max_scrape_workers", 10),
                timeout=getattr(settings, "scrape_timeout_seconds", 3.5),
                max_chars=getattr(settings, "max_article_text_chars", 3500),
            )

            # 4. Extract knowledge graph using LLM (parallel chunked batches)
            extracted = self.extractor.extract(new_articles)

            # Bug #1 fix: track how many articles the LLM failed on
            failed_article_count = extracted.pop("failed_article_count", 0)

            # 5. Persist extraction transactionally
            stats = self.writer.persist_extraction(new_articles, extracted)

            job.articles_processed = len(new_articles) - failed_article_count
            job.articles_failed = failed_article_count
            job.entities_created = stats.get("entities_created", 0)
            job.entities_updated = stats.get("entities_updated", 0)
            job.events_created = stats.get("events_created", 0)
            job.relationships_created = stats.get("relationships_created", 0)

            # Bug #1 fix: report partial_success when some articles fail
            if failed_article_count > 0 and job.articles_processed > 0:
                job.status = "partial_success"
                job.error_details = f"{failed_article_count} article(s) failed LLM extraction"
            elif failed_article_count > 0 and job.articles_processed == 0:
                job.status = "failed"
                job.error_details = "All articles failed LLM extraction"
            else:
                job.status = "completed"

            job.completed_at = utc_now_iso()
            GraphStore.record_job(job)
            logger.info(f"[Pipeline] Job {job_id} finished ({job.status}): {stats}")
            return job

        except Exception as e:
            job.status = "failed"
            job.completed_at = utc_now_iso()
            job.error_details = str(e)
            GraphStore.record_job(job)
            logger.error(f"[Pipeline] Job {job_id} failed: {e}")
            raise
