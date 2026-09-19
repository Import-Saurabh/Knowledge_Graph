"""Background ingestion scheduler using APScheduler."""
from __future__ import annotations

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