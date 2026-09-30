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
    assert "links" in data


def test_conversations_flow():
    # 1. Create conversation
    create_res = client.post("/api/conversations", json={"title": "Test Chat Flow"})
    assert create_res.status_code == 200
    conv = create_res.json()
    conv_id = conv["id"]
    assert conv["title"] == "Test Chat Flow"

    # 2. Get conversation
    get_res = client.get(f"/api/conversations/{conv_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == conv_id

    # 3. List conversations
    list_res = client.get("/api/conversations")
    assert list_res.status_code == 200
    assert any(c["id"] == conv_id for c in list_res.json())


def test_ingest_auth_protection():
    # Attempt without API key -> 403 Forbidden
    unauth_res = client.post("/api/ingest", json={"force": False})
    assert unauth_res.status_code == 403

    # Attempt with wrong API key -> 403 Forbidden
    wrong_res = client.post(
        "/api/ingest",
        json={"force": False},
        headers={"X-API-Key": "wrong-secret-key"},
    )
    assert wrong_res.status_code == 403


def test_static_page_serves():
    # Root 3D graph page
    root_res = client.get("/")
    assert root_res.status_code == 200
    assert "text/html" in root_res.headers.get("content-type", "")

    # Graph chat page
    chat_res = client.get("/chat")
    assert chat_res.status_code == 200
    assert "text/html" in chat_res.headers.get("content-type", "")

    # graph.json
    graph_res = client.get("/graph.json")
    assert graph_res.status_code == 200
