"""Report ingestion endpoints (Phase 1A).

Routes are thin: they parse/shape HTTP, delegate to the service/repository, and
return schemas. No business logic lives here (docs/09 §). Mounted under
`/api/v1/reports`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.ingestion.services.report_ingestion_service import ReportIngestionService
from app.models.enums import ReportType
from app.repositories.report_repository import ReportRepository
from app.schemas.report import (
    ReportDetail,
    ReportListItem,
    ReportListResponse,
    ReportPageOut,
    ReportPagesResponse,
    ReportUploadResponse,
)

router = APIRouter()


@router.post(
    "/upload",
    response_model=ReportUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a financial PDF for ingestion",
)
async def upload_report(
    file: UploadFile = File(..., description="PDF document (10-K, 10-Q, transcript)"),
    report_type: ReportType = Form(...),
    year: int = Form(..., ge=1900, le=2200),
    quarter: int | None = Form(None, ge=1, le=4),
    ticker: str | None = Form(None, max_length=16),
    company_name: str | None = Form(None, max_length=255),
    db: AsyncSession = Depends(get_db),
) -> ReportUploadResponse:
    """Store the file, create a report record, and queue async processing."""
    data = await file.read()
    service = ReportIngestionService(db)
    report = await service.ingest_upload(
        data=data,
        original_filename=file.filename,
        content_type=file.content_type,
        report_type=report_type,
        year=year,
        quarter=quarter,
        ticker=ticker,
        company_name=company_name,
    )
    return ReportUploadResponse(report_id=report.id, status=report.status)


@router.get("", response_model=ReportListResponse, summary="List reports")
async def list_reports(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> ReportListResponse:
    repo = ReportRepository(db)
    rows, total = await repo.list_reports(limit=limit, offset=offset)
    return ReportListResponse(
        items=[ReportListItem.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{report_id}", response_model=ReportDetail, summary="Get report detail")
async def get_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ReportDetail:
    repo = ReportRepository(db)
    report = await repo.get_report(report_id)
    if report is None:
        raise NotFoundError("Report not found", details={"report_id": str(report_id)})
    return ReportDetail.model_validate(report)


@router.get(
    "/{report_id}/pages",
    response_model=ReportPagesResponse,
    summary="Get extracted page text (debugging)",
)
async def get_report_pages(
    report_id: uuid.UUID,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> ReportPagesResponse:
    repo = ReportRepository(db)
    report = await repo.get_report(report_id)
    if report is None:
        raise NotFoundError("Report not found", details={"report_id": str(report_id)})
    pages, total = await repo.get_pages(report_id, limit=limit, offset=offset)
    return ReportPagesResponse(
        report_id=report_id,
        total_pages=total,
        items=[ReportPageOut.model_validate(p) for p in pages],
        limit=limit,
        offset=offset,
    )
