"""Background ingestion scheduler using APScheduler."""
from __future__ import annotations

import os
import sys
import threading
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from server.config import settings
from server.ingestion.pipeline import IngestionPipeline

_scheduler: Optional[BackgroundScheduler] = None
_job_lock = threading.Lock()


def run_scheduled_ingestion():
    """Worker task executed periodically by the background scheduler."""
    if not _job_lock.acquire(blocking=False):
        print("[Scheduler] Ingestion job already in progress, skipping overlapping run.")
        return

    try:
        print("[Scheduler] Triggering scheduled news ingestion...")
        pipeline = IngestionPipeline()
        pipeline.run(trigger="scheduler", force=False)
    except Exception as e:
        print(f"[Scheduler] Error during scheduled ingestion: {e}", file=sys.stderr)
    finally:
        _job_lock.release()


def start_scheduler() -> Optional[BackgroundScheduler]:
    """Start the background scheduler if enabled."""
    global _scheduler
    if not settings.scheduler_enabled:
        print("[Scheduler] Background scheduler is disabled in configuration.")
        return None

    if _scheduler is not None and _scheduler.running:
        return _scheduler

    from datetime import datetime, timezone

    scheduler = BackgroundScheduler(daemon=True)

    # Calculate schedule interval: default to minutes for real-time news sync
    if settings.ingestion_schedule_hours and settings.ingestion_schedule_hours > 0 and not os.environ.get("INGESTION_SCHEDULE_MINUTES"):
        hours = max(1, settings.ingestion_schedule_hours)
        trigger = IntervalTrigger(hours=hours)
        schedule_desc = f"every {hours} hour(s)"
    else:
        minutes = max(1, settings.ingestion_schedule_minutes or 2)
        trigger = IntervalTrigger(minutes=minutes)
        schedule_desc = f"every {minutes} minute(s)"

    # Trigger immediately at current timestamp so news is ingested right away without waiting
    start_time = datetime.now(timezone.utc)
    scheduler.add_job(
        run_scheduled_ingestion,
        trigger=trigger,
        next_run_time=start_time,
        id="news_ingestion_scheduled",
        name="Scheduled News Ingestion",
        replace_existing=True,
    )
    scheduler.start()
    _scheduler = scheduler
    print(f"[Scheduler] Background scheduler started ({schedule_desc}, initial ingestion triggered at {start_time.isoformat()}).")
    return _scheduler


def shutdown_scheduler():
    """Gracefully stop the background scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("[Scheduler] Background scheduler stopped.")
        _scheduler = None
