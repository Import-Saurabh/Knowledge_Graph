"""Graph Chat query and conversation endpoints."""
from __future__ import annotations

import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.database import GraphStore
from server.models import QueryRequest, QueryResponse
from server.query.engine import QueryEngine

router = APIRouter(prefix="/api", tags=["query"])
_query_engine = QueryEngine()


class CreateConversationRequest(BaseModel):
    title: Optional[str] = "New Conversation"


@router.post("/query", response_model=QueryResponse)
def execute_query(req: QueryRequest):
    """Run graph-grounded research and synthesize an evidence-backed answer."""
    if not req.question or not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    try:
        return _query_engine.answer_question(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@router.get("/conversations")
def list_conversations(limit: int = 50):
    """List recent conversation sessions."""
    return GraphStore.list_conversations(limit=limit)


@router.post("/conversations")
def create_conversation(req: CreateConversationRequest):
    """Create a new conversation session."""
    conv_id = str(uuid.uuid4())
    conv = GraphStore.create_conversation(conv_id, title=req.title or "New Conversation")
    return conv.model_dump()


@router.get("/conversations/{conversation_id}")
def get_conversation_history(conversation_id: str):
    """Retrieve conversation details and chronological messages."""
    conv = GraphStore.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conv
