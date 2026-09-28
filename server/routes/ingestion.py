"""Ingestion management and status endpoints."""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query

from server.config import settings
from server.database import GraphStore
from server.ingestion.pipeline import IngestionPipeline
from server.models import IngestRequest, IngestResponse

router = APIRouter(prefix="/api/ingest", tags=["ingestion"])


@router.post("", response_model=IngestResponse)
def trigger_ingestion(
    req: IngestRequest,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None),
):
    """Trigger manual news ingestion (requires admin API key)."""
    key = x_api_key or api_key
    if key != settings.admin_api_key:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Invalid or missing administrative API key.",
        )

    pipeline = IngestionPipeline()
    try:
        job = pipeline.run(
            trigger="api_manual",
            max_per_feed=req.max_articles_per_feed,
            force=req.force,
        )
        return IngestResponse(
            job_id=job.id,
            status=job.status,
            message="Ingestion run completed.",
            stats={
                "discovered": job.articles_discovered,
                "processed": job.articles_processed,
                "skipped": job.articles_skipped,
                "entities_created": job.entities_created,
                "events_created": job.events_created,
                "relationships_created": job.relationships_created,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@router.get("/status")
def get_ingestion_history(limit: int = 20):
    """Retrieve history of background and manual ingestion jobs."""
    return GraphStore.list_jobs(limit=limit)
