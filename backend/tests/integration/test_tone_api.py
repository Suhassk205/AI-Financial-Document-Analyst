"""Integration tests for Phase 5 Management Tone API and Celery Tasks."""

from __future__ import annotations

import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session
from unittest.mock import patch

from app.core.config import settings
from app.models.company import Company
from app.models.report import Report
from app.models.document_chunk import DocumentChunk
from app.models.enums import ReportStatus, ReportType, Sentiment, ConfidenceLevel, ToneEvolutionType
from app.models.management_tone import ManagementTone
from app.models.tone_evolution import ToneEvolution
from app.tasks.ingestion import extract_management_tone_task

PREFIX = settings.api_v1_prefix


def _seed_company_and_reports(session: Session):
    company = Company(
        name="Tone Test Company",
        ticker="TTC",
        sector="Technology",
        industry="Software"
    )
    session.add(company)
    session.commit()

    # Seed 2023 report (previous period)
    report_2023 = Report(
        company_id=company.id,
        report_type=ReportType.TEN_K,
        year=2023,
        original_filename="ttc_2023_10k.pdf",
        storage_path="reports/2023/ttc_2023_10k.pdf",
        status=ReportStatus.CHUNKED,
        total_pages=1
    )
    session.add(report_2023)
    session.commit()

    # Seed 2024 report (current period)
    report_2024 = Report(
        company_id=company.id,
        report_type=ReportType.TEN_K,
        year=2024,
        original_filename="ttc_2024_10k.pdf",
        storage_path="reports/2024/ttc_2024_10k.pdf",
        status=ReportStatus.CHUNKED,
        total_pages=1
    )
    session.add(report_2024)
    session.commit()

    # Seed chunks for 2023 (Negative/Cautious tone)
    chunk_2023 = DocumentChunk(
        report_id=report_2023.id,
        chunk_index=0,
        chunk_text="We face significant headwinds. The volatile market may disrupt our operations.",
        token_count=15,
        chunk_metadata={"normalized_section_name": "Management Commentary", "report_id": str(report_2023.id)}
    )
    session.add(chunk_2023)

    # Seed chunks for 2024 (Positive/Confident tone)
    chunk_2024 = DocumentChunk(
        report_id=report_2024.id,
        chunk_index=0,
        chunk_text="Our company delivered exceptional performance. We expect continued growth.",
        token_count=17,
        chunk_metadata={"normalized_section_name": "Management Commentary", "report_id": str(report_2024.id)}
    )
    session.add(chunk_2024)

    session.commit()
    return company.id, report_2023.id, report_2024.id


@pytest.mark.integration
def test_tone_tasks_ingestion_and_evolution(sync_session: Session) -> None:
    company_id, report_2023_id, report_2024_id = _seed_company_and_reports(sync_session)

    # 1. Run tone extraction for 2023 report
    res_2023 = extract_management_tone_task(str(report_2023_id))
    assert res_2023["status"] == "READY"
    assert res_2023["tones"] >= 1
    assert res_2023["evolutions"] == 0  # No prior report to compare against yet

    # Verify report status is now READY
    report_2023 = sync_session.get(Report, report_2023_id)
    assert report_2023.status == ReportStatus.READY

    # Verify tone record was created
    t_2023 = sync_session.query(ManagementTone).filter_by(report_id=report_2023_id).all()
    assert len(t_2023) >= 1
    assert t_2023[0].sentiment == Sentiment.NEGATIVE
    assert t_2023[0].confidence_level == ConfidenceLevel.VERY_CAUTIOUS

    # 2. Run tone extraction for 2024 report (should trigger evolution logic against 2023)
    res_2024 = extract_management_tone_task(str(report_2024_id))
    assert res_2024["status"] == "READY"
    assert res_2024["tones"] >= 1
    assert res_2024["evolutions"] >= 1

    report_2024 = sync_session.get(Report, report_2024_id)
    assert report_2024.status == ReportStatus.READY

    t_2024 = sync_session.query(ManagementTone).filter_by(report_id=report_2024_id).all()
    assert len(t_2024) >= 1
    assert t_2024[0].sentiment == Sentiment.POSITIVE
    assert t_2024[0].confidence_level == ConfidenceLevel.VERY_CONFIDENT

    # Verify tone evolution record was created
    evolutions = sync_session.query(ToneEvolution).filter_by(company_id=company_id).all()
    assert len(evolutions) >= 1
    # Check that it's MORE_POSITIVE since it went from NEGATIVE to POSITIVE
    assert evolutions[0].evolution_type == ToneEvolutionType.MORE_POSITIVE
    assert evolutions[0].previous_tone_id == t_2023[0].id
    assert evolutions[0].current_tone_id == t_2024[0].id


@pytest.mark.integration
async def test_tone_api_endpoints(api_client: AsyncClient, sync_session: Session) -> None:
    company_id, report_2023_id, report_2024_id = _seed_company_and_reports(sync_session)

    # Ingest and generate evolution
    extract_management_tone_task(str(report_2023_id))
    extract_management_tone_task(str(report_2024_id))

    # Test GET /reports/{report_id}/tone
    resp = await api_client.get(f"{PREFIX}/reports/{report_2024_id}/tone")
    assert resp.status_code == 200
    listing = resp.json()
    assert len(listing) >= 1
    tone = listing[0]
    assert tone["sentiment"] == "POSITIVE"
    assert tone["confidence_level"] == "VERY_CONFIDENT"
    assert tone["source_type"] == "Management Commentary"

    # Test GET /reports/{report_id}/tone/{tone_id}
    tone_id = tone["id"]
    resp_det = await api_client.get(f"{PREFIX}/reports/{report_2024_id}/tone/{tone_id}")
    assert resp_det.status_code == 200
    detail = resp_det.json()
    assert detail["id"] == tone_id
    assert detail["sentiment"] == "POSITIVE"

    # Test POST /reports/{report_id}/tone/extract
    resp_ext = await api_client.post(f"{PREFIX}/reports/{report_2024_id}/tone/extract")
    assert resp_ext.status_code == 202
    assert resp_ext.json()["task_enqueued"] is True

    # Test GET /companies/{company_id}/tone
    resp_co = await api_client.get(f"{PREFIX}/companies/{company_id}/tone")
    assert resp_co.status_code == 200
    co_tone = resp_co.json()
    assert len(co_tone) >= 2  # one from 2023, one from 2024

    # Test GET /companies/{company_id}/tone-evolution
    resp_evol = await api_client.get(f"{PREFIX}/companies/{company_id}/tone-evolution")
    assert resp_evol.status_code == 200
    evol_listing = resp_evol.json()
    assert len(evol_listing) >= 1
    evol_row = evol_listing[0]
    assert evol_row["evolution_type"] == "MORE_POSITIVE"

    # Test GET /companies/{company_id}/tone-summary
    resp_sum = await api_client.get(f"{PREFIX}/companies/{company_id}/tone-summary")
    assert resp_sum.status_code == 200
    summary = resp_sum.json()
    assert summary["company_id"] == str(company_id)
    assert len(summary["sections"]) >= 1
    # Check that there is a summary for "Management Commentary"
    commentary_sum = next(s for s in summary["sections"] if s["source_type"] == "Management Commentary")
    assert commentary_sum["average_hedging_score"] >= 0.0
