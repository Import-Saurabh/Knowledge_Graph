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
)

# Include API routers
app.include_router(graph_router)
app.include_router(query_router)
app.include_router(ingestion_router)


@app.get("/api/health", response_model=HealthResponse, tags=["system"])
def health_check():
    """Verify service health and database integrity."""
    db_status = "unhealthy"
    ent_count = 0
    rel_count = 0
    art_count = 0
    last_ingestion = None

    try:
        with get_db() as conn:
            ent_count = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
            rel_count = conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
            art_count = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
            job_row = conn.execute("SELECT completed_at FROM ingestion_jobs WHERE status = 'completed' ORDER BY started_at DESC LIMIT 1").fetchone()
            if job_row and job_row[0]:
                last_ingestion = job_row[0]
            db_status = "healthy"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return HealthResponse(
        status="healthy" if db_status == "healthy" else "degraded",
        version=settings.version,
        database=db_status,
        entity_count=ent_count,
        relationship_count=rel_count,
        article_count=art_count,
        last_ingestion=last_ingestion,
    )


# ---------------------------------------------------------------------------
# Static Site & Page Routes
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent


@app.get("/", include_in_schema=False)
def serve_root():
    """Serve the primary 3D Knowledge Graph visualization."""
    return FileResponse(BASE_DIR / "index.html")


@app.get("/chat", include_in_schema=False)
def serve_chat():
    """Serve the dedicated Graph Chat workspace."""
    chat_file = BASE_DIR / "chat.html"
    if chat_file.exists():
        return FileResponse(chat_file)
    return FileResponse(BASE_DIR / "index.html")


@app.get("/graph.json", include_in_schema=False)
def serve_graph_json():
    """Serve the active knowledge graph data payload."""
    graph_file = BASE_DIR / "graph.json"
    return FileResponse(graph_file, media_type="application/json")


@app.get("/version.json", include_in_schema=False)
def serve_version_json():
    """Serve the version metadata."""
    v_file = BASE_DIR / "version.json"
    if v_file.exists():
        return FileResponse(v_file, media_type="application/json")
    return {"version": settings.version, "sha": "local"}


# Serve static assets (images, favicon, etc.)
for asset in ["favicon.svg", "apple-touch-icon.png", "og-image.png", "photo.jpg", "robots.txt", "sitemap.xml"]:
    p = BASE_DIR / asset
    if p.exists():
        app.add_api_route(f"/{asset}", lambda path=p: FileResponse(path), include_in_schema=False)
