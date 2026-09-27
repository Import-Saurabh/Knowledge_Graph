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