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