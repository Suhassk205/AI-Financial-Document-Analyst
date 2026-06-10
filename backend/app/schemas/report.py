"""Pydantic request/response schemas for report ingestion (Phase 1A)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ReportStatus, ReportType


class ReportUploadResponse(BaseModel):
    """Returned immediately after a successful upload (processing is async)."""

    report_id: uuid.UUID
    status: ReportStatus


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    ticker: str | None = None
    sector: str | None = None
    industry: str | None = None


class ReportDetail(BaseModel):
    """Full report metadata + processing status."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID | None = None
    report_type: ReportType
    year: int
    quarter: int | None = None
    original_filename: str
    storage_path: str
    status: ReportStatus
    total_pages: int | None = None
    error_message: str | None = None
    processing_started_at: datetime | None = None
    processing_completed_at: datetime | None = None
    uploaded_at: datetime
    updated_at: datetime


class ReportListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID | None = None
    report_type: ReportType
    year: int
    quarter: int | None = None
    original_filename: str
    status: ReportStatus
    total_pages: int | None = None
    uploaded_at: datetime


class ReportListResponse(BaseModel):
    items: list[ReportListItem]
    total: int
    limit: int
    offset: int


class ReportPageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    page_number: int
    page_text: str


class ReportPagesResponse(BaseModel):
    """Paginated page text — used to debug extraction quality."""

    report_id: uuid.UUID
    total_pages: int
    items: list[ReportPageOut]
    limit: int
    offset: int
