"""Main FastAPI application for DriftForge News Intelligence Platform."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from server.config import settings
from server.database import GraphStore, get_db, init_db
from server.models import HealthResponse
from server.routes.graph import router as graph_router
from server.routes.ingestion import router as ingestion_router
from server.routes.query import router as query_router
from server.scheduler import shutdown_scheduler, start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database and start background ingestion scheduler
    init_db()
    start_scheduler()
    yield
    # Shutdown: cleanly stop background tasks
    shutdown_scheduler()


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="Persistent, evidence-backed news intelligence knowledge graph with Graph Chat.",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],