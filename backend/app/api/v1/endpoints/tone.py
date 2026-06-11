"""Management tone API endpoints (Phase 5)."""

from __future__ import annotations

import uuid
from collections import defaultdict
from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.enums import Sentiment
from app.models.management_tone import ManagementTone
from app.models.tone_evolution import ToneEvolution
from app.repositories.report_repository import ReportRepository
from app.schemas.tone import (
    ManagementToneResponse,
    ToneEvolutionResponse,
    CompanyToneSummary,
    ToneSectionSummary,
)
from app.tasks.ingestion import extract_management_tone_task

router = APIRouter()


def _tone_out(t: ManagementTone) -> ManagementToneResponse:
    return ManagementToneResponse(
        id=t.id,
        company_id=t.company_id,
        report_id=t.report_id,
        source_chunk_id=t.source_chunk_id,
        source_type=t.source_type,
        sentiment=Sentiment(t.sentiment),
        confidence_level=t.confidence_level,
        hedging_score=float(t.hedging_score),
        positive_score=float(t.positive_score),
        negative_score=float(t.negative_score),
        confidence_score=float(t.confidence_score),
        extraction_method=t.extraction_method,
        source_text=t.source_text,
        extraction_metadata={},
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


def _evolution_out(e: ToneEvolution) -> ToneEvolutionResponse:
    return ToneEvolutionResponse(
        id=e.id,
        company_id=e.company_id,
        current_tone_id=e.current_tone_id,
        previous_tone_id=e.previous_tone_id,
        evolution_type=e.evolution_type,
        confidence_score=float(e.confidence_score),
        explanation=e.explanation,
        created_at=e.created_at,
        updated_at=e.updated_at,
    )


@router.get(
    "/reports/{report_id}/tone",
    response_model=list[ManagementToneResponse],
    summary="List management tone extractions for a report",
)
async def list_report_tone(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[ManagementToneResponse]:
    repo = ReportRepository(db)
    if await repo.get_report(report_id) is None:
        raise NotFoundError("Report not found", details={"report_id": str(report_id)})
    tones = await repo.get_tone_by_report(report_id)
    return [_tone_out(t) for t in tones]


@router.get(
    "/reports/{report_id}/tone/{tone_id}",
    response_model=ManagementToneResponse,
    summary="Get details of a specific management tone record",
)
async def get_report_tone_detail(
    report_id: uuid.UUID,
    tone_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ManagementToneResponse:
    repo = ReportRepository(db)
    tone = await repo.get_tone_by_id(tone_id)
    if tone is None or tone.report_id != report_id:
        raise NotFoundError("Management tone record not found", details={"tone_id": str(tone_id)})
    return _tone_out(tone)


@router.post(
    "/reports/{report_id}/tone/extract",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger management tone extraction task",
)
async def trigger_tone_extraction(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = ReportRepository(db)
    report = await repo.get_report(report_id)
    if report is None:
        raise NotFoundError("Report not found", details={"report_id": str(report_id)})

    # Ensure report has chunks to extract from
    chunks_count = await repo.count_chunks_async(report_id)
    if chunks_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Report has no chunks to extract from (run chunking first).",
        )

    extract_management_tone_task.delay(str(report_id))
    return {
        "report_id": report_id,
        "report_status": report.status,
        "task_enqueued": True,
        "detail": "Management tone extraction queued.",
    }


@router.get(
    "/companies/{company_id}/tone",
    response_model=list[ManagementToneResponse],
    summary="List all management tone records for a company across reports",
)
async def list_company_tone(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[ManagementToneResponse]:
    repo = ReportRepository(db)
    if await repo.get_company(company_id) is None:
        raise NotFoundError("Company not found", details={"company_id": str(company_id)})
    tones = await repo.get_tone_by_company(company_id)
    return [_tone_out(t) for t in tones]


@router.get(
    "/companies/{company_id}/tone-evolution",
    response_model=list[ToneEvolutionResponse],
    summary="List all tone evolution records for a company",
)
async def list_company_tone_evolution(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[ToneEvolutionResponse]:
    repo = ReportRepository(db)
    if await repo.get_company(company_id) is None:
        raise NotFoundError("Company not found", details={"company_id": str(company_id)})
    evolutions = await repo.get_tone_evolutions_by_company(company_id)
    return [_evolution_out(e) for e in evolutions]


@router.get(
    "/companies/{company_id}/tone-summary",
    response_model=CompanyToneSummary,
    summary="Get aggregated tone summary metrics for a company",
)
async def get_company_tone_summary(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> CompanyToneSummary:
    repo = ReportRepository(db)
    if await repo.get_company(company_id) is None:
        raise NotFoundError("Company not found", details={"company_id": str(company_id)})

    tones = await repo.get_tone_by_company(company_id)
    if not tones:
        return CompanyToneSummary(
            company_id=company_id,
            total_tone_records=0,
            overall_average_positive=0.0,
            overall_average_negative=0.0,
            overall_average_hedging=0.0,
            overall_average_confidence=0.0,
            sections=[],
        )

    overall_pos = 0.0
    overall_neg = 0.0
    overall_hedge = 0.0
    overall_conf = 0.0

    by_section = defaultdict(list)
    for t in tones:
        overall_pos += float(t.positive_score)
        overall_neg += float(t.negative_score)
        overall_hedge += float(t.hedging_score)
        overall_conf += float(t.confidence_score)
        by_section[t.source_type].append(t)

    total = len(tones)
    sections_summary = []
    for section_type, records in by_section.items():
        sec_pos = sum(float(r.positive_score) for r in records) / len(records)
        sec_neg = sum(float(r.negative_score) for r in records) / len(records)
        sec_hedge = sum(float(r.hedging_score) for r in records) / len(records)
        sec_conf = sum(float(r.confidence_score) for r in records) / len(records)

        # Dominant sentiment calculation
        if sec_pos > sec_neg + 0.01:
            dom_sent = Sentiment.POSITIVE
        elif sec_neg > sec_pos + 0.01:
            dom_sent = Sentiment.NEGATIVE
        else:
            dom_sent = Sentiment.NEUTRAL

        sections_summary.append(
            ToneSectionSummary(
                source_type=section_type,
                average_positive_score=round(sec_pos, 3),
                average_negative_score=round(sec_neg, 3),
                average_hedging_score=round(sec_hedge, 3),
                average_confidence_score=round(sec_conf, 3),
                dominant_sentiment=dom_sent,
                record_count=len(records),
            )
        )

    # Sort sections by name
    sections_summary.sort(key=lambda x: x.source_type)

    return CompanyToneSummary(
        company_id=company_id,
        total_tone_records=total,
        overall_average_positive=round(overall_pos / total, 3),
        overall_average_negative=round(overall_neg / total, 3),
        overall_average_hedging=round(overall_hedge / total, 3),
        overall_average_confidence=round(overall_conf / total, 3),
        sections=sections_summary,
    )
