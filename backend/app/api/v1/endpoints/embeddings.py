"""Embedding operational endpoints (Phase 2A). Mounted under /api/v1/reports.

Purpose: operational monitoring + control of embedding generation —
  * POST .../embeddings/generate  → trigger an async embedding run
  * GET  .../embeddings/status    → per-status chunk counts + report status
  * GET  .../embeddings/stats     → coverage (total / embedded / missing / dim)

These are NOT retrieval endpoints. There is deliberately no similarity-search or
nearest-neighbour route here — that is Phase 2B.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.enums import EmbeddingStatus
from app.repositories.report_repository import ReportRepository
from app.schemas.embedding import (
    EmbeddingGenerateResponse,
    EmbeddingStatsResponse,
    EmbeddingStatusResponse,
)
from app.tasks.ingestion import generate_embeddings_task

router = APIRouter()


@router.post(
    "/{report_id}/embeddings/generate",
    response_model=EmbeddingGenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger embedding generation for a report's chunks",
)
async def generate_embeddings(
    report_id: uuid.UUID,
    force: bool = Query(
        False, description="Re-embed every chunk (default: only chunks missing a vector)"
    ),
    db: AsyncSession = Depends(get_db),
) -> EmbeddingGenerateResponse:
    repo = ReportRepository(db)
    report = await repo.get_report(report_id)
    if report is None:
        raise NotFoundError("Report not found", details={"report_id": str(report_id)})

    total = await repo.count_chunks_async(report_id)
    if total == 0:
        # Nothing to embed yet — chunks come from Phase 1C.
        return EmbeddingGenerateResponse(
            report_id=report_id,
            report_status=report.status,
            task_enqueued=False,
            force=force,
            detail="Report has no chunks to embed (run chunking first).",
        )

    generate_embeddings_task.delay(str(report_id), force=force)
    return EmbeddingGenerateResponse(
        report_id=report_id,
        report_status=report.status,
        task_enqueued=True,
        force=force,
        detail=f"Embedding run queued for {total} chunk(s).",
    )


@router.get(
    "/{report_id}/embeddings/status",
    response_model=EmbeddingStatusResponse,
    summary="Per-status embedding counts for a report",
)
async def embedding_status(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> EmbeddingStatusResponse:
    repo = ReportRepository(db)
    report = await repo.get_report(report_id)
    if report is None:
        raise NotFoundError("Report not found", details={"report_id": str(report_id)})

    counts = await repo.get_embedding_status_counts(report_id)
    total = sum(counts.values())
    return EmbeddingStatusResponse(
        report_id=report_id,
        report_status=report.status,
        total_chunks=total,
        pending=counts.get(EmbeddingStatus.PENDING.value, 0),
        processing=counts.get(EmbeddingStatus.PROCESSING.value, 0),
        completed=counts.get(EmbeddingStatus.COMPLETED.value, 0),
        failed=counts.get(EmbeddingStatus.FAILED.value, 0),
    )


@router.get(
    "/{report_id}/embeddings/stats",
    response_model=EmbeddingStatsResponse,
    summary="Embedding coverage stats (total / embedded / missing / dimension)",
)
async def embedding_stats(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> EmbeddingStatsResponse:
    repo = ReportRepository(db)
    report = await repo.get_report(report_id)
    if report is None:
        raise NotFoundError("Report not found", details={"report_id": str(report_id)})

    total = await repo.count_chunks_async(report_id)
    embedded = await repo.count_embedded_async(report_id)
    missing = total - embedded
    return EmbeddingStatsResponse(
        report_id=report_id,
        total_chunks=total,
        embedded_chunks=embedded,
        missing_chunks=missing,
        dimension=settings.embedding_dim,
        model=settings.gemini_embedding_model,
        fully_embedded=(total > 0 and missing == 0),
    )
