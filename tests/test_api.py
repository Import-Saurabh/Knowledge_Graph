"""Integration tests for FastAPI endpoints."""
import pytest
from fastapi.testclient import TestClient

from server.app import app
from server.config import settings

client = TestClient(app)


def test_health_endpoint():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["database"] == "healthy"
    assert "version" in data
    assert "entity_count" in data


def test_graph_endpoint():
    res = client.get("/api/graph")
    assert res.status_code == 200
    data = res.json()
    assert "nodes" in data
    assert "links" in data
    assert "entity_count" in data
    assert isinstance(data["nodes"], list)


def test_subgraph_endpoint():
    res = client.get("/api/graph/subgraph?nodes=russia,ukraine&hops=1")
    assert res.status_code == 200
    data = res.json()
    assert "nodes" in data