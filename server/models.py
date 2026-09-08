"""Pydantic models and schemas for DriftForge."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Domain Models
# ---------------------------------------------------------------------------

class EntityType(str, Enum):
    PERSON = "person"
    ORGANISATION = "organisation"
    COUNTRY = "country"
    LOCATION = "location"
    GOVERNMENT = "government"
    EVENT = "event"
    CONCEPT = "concept"
    ARMED_GROUP = "armed_group"
    INFRASTRUCTURE = "infrastructure"


class Entity(BaseModel):
    id: str
    entity_type: str
    canonical_name: str
    description: Optional[str] = None
    aliases: list[str] = Field(default_factory=list)
    external_ids: dict[str, str] = Field(default_factory=dict)
    first_observed_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Event(BaseModel):
    id: str
    event_type: str
    summary: str
    event_time: Optional[str] = None
    event_time_precision: str = "day"  # exact | day | week | approximate
    location: Optional[str] = None
    status: str = "reported"  # reported | confirmed | denied | retracted
    confidence: float = 0.8
    first_observed_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Article(BaseModel):
    id: str
    url: str
    url_hash: str
    publisher: Optional[str] = None
    headline: Optional[str] = None
    summary: Optional[str] = None
    content_excerpt: Optional[str] = None
    content_hash: Optional[str] = None
    author: Optional[str] = None
    language: str = "en"
    published_at: Optional[str] = None
    ingested_at: str = Field(default_factory=utc_now_iso)
    feed_source: Optional[str] = None
    extraction_status: str = "pending"  # pending | extracted | failed | skipped
    metadata: dict[str, Any] = Field(default_factory=dict)


class Relationship(BaseModel):
    id: str
    source_id: str
    target_id: str
    relationship_type: str
    description: Optional[str] = None
    source_article_id: Optional[str] = None
    first_observed_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Claim(BaseModel):
    id: str
    claim_text: str
    subject_entity_id: Optional[str] = None
    predicate: Optional[str] = None
    object_entity_id: Optional[str] = None
    source_article_id: str
    attribution: Optional[str] = None
    claim_type: str = "media_report"  # official_claim | media_report | corroborated
    confidence: float = 0.8
    event_id: Optional[str] = None
    observed_at: str = Field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Conversation(BaseModel):
    id: str
    title: Optional[str] = "New Conversation"
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class Message(BaseModel):
    id: str
    conversation_id: str
    role: str  # user | assistant
    content: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)
    research_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)


class IngestionJob(BaseModel):