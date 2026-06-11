"""Agent-related Pydantic validation schemas (Phase 7).

Ensures correct format of request payloads and API responses.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str
    thread_id: str
    company_id: uuid.UUID | None = None


class CitationOut(BaseModel):
    source_text: str
    citation_id: str | None = None
    page_number: int | None = None
    section_name: str | None = None


class ChatResponse(BaseModel):
    answer: str
    key_findings: list[str] = Field(default_factory=list)
    citations: list[CitationOut] = Field(default_factory=list)


class ThreadCreate(BaseModel):
    company_id: uuid.UUID | None = None


class ThreadOut(BaseModel):
    id: uuid.UUID
    thread_id: str
    company_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MessageOut(BaseModel):
    id: uuid.UUID
    thread_id: uuid.UUID
    role: str
    content: str
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True
        # Allow loading from object with attribute message_metadata as metadata
        populate_by_name = True
