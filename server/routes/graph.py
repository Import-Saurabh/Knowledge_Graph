"""Graph querying and visualization endpoints."""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from server.database import GraphStore
from server.models import GraphResponse

router = APIRouter(prefix="/api", tags=["graph"])


@router.get("/graph", response_model=GraphResponse)
def get_graph(limit: int = Query(default=500, ge=10, le=2000)):
    """Retrieve full graph snapshot for 3D force graph visualization."""
    data = GraphStore.get_all_graph_data(limit_nodes=limit)
    return GraphResponse(**data)


@router.get("/graph/subgraph")
def get_subgraph(
    nodes: str = Query(..., description="Comma-separated entity IDs"),
    hops: int = Query(default=1, ge=1, le=3),
):
    """Retrieve neighborhood subgraph centered on specific nodes."""
    node_ids = [n.strip() for n in nodes.split(",") if n.strip()]
    if not node_ids:
        raise HTTPException(status_code=400, detail="At least one node ID must be provided.")
    return GraphStore.get_subgraph(node_ids, max_hops=hops)
