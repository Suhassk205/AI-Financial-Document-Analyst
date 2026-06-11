"""Pydantic schemas for the embedding operational endpoints (Phase 2A).

These endpoints exist for operational monitoring — "does every chunk have a
valid embedding?" — NOT for retrieval. Similarity search is Phase 2B.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.models.enums import ReportStatus


class EmbeddingGenerateResponse(BaseModel):
    """Returned after queueing an embedding run (processing is async)."""

    report_id: uuid.UUID
    report_status: ReportStatus
    task_enqueued: bool
    force: bool
    detail: str


class EmbeddingStatusResponse(BaseModel):
    """Per-status chunk counts + the report's overall status."""

    report_id: uuid.UUID
    report_status: ReportStatus
    total_chunks: int
    pending: int
    processing: int
    completed: int
    failed: int


class EmbeddingStatsResponse(BaseModel):
    """Coverage stats. `embedded_chunks` counts chunks with a stored vector.

    Matches the task §10 contract, e.g.:
        {"total_chunks": 152, "embedded_chunks": 152, "missing_chunks": 0, "dimension": 768}
    """

    report_id: uuid.UUID
    total_chunks: int
    embedded_chunks: int
    missing_chunks: int
    dimension: int
    model: str
    fully_embedded: bool
