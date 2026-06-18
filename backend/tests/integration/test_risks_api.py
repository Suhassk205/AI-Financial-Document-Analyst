"""Integration tests for Phase 4 Risks API and Celery Tasks."""

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
from app.models.enums import ReportStatus, ReportType
from app.models.risk_factor import RiskFactor
from app.models.risk_evolution import RiskEvolution
from app.tasks.ingestion import extract_risks_task, generate_risk_evolution_task

PREFIX = settings.api_v1_prefix


def _seed_company_and_reports(session: Session):
    company = Company(
        name="Test Company",
        ticker="TST",
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
        original_filename="tst_2023_10k.pdf",
        storage_path="reports/2023/tst_2023_10k.pdf",
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
        original_filename="tst_2024_10k.pdf",
        storage_path="reports/2024/tst_2024_10k.pdf",
        status=ReportStatus.CHUNKED,
        total_pages=1
    )
    session.add(report_2024)
    session.commit()

    # Seed chunks for 2023 (Low severity supply chain risk)
    chunk_2023 = DocumentChunk(
        report_id=report_2023.id,
        chunk_index=0,
        chunk_text="We have a minor risk of supply chain delays due to single source vendors.",
        token_count=15,
        chunk_metadata={"normalized_section_name": "Risk Factors", "report_id": str(report_2023.id)}
    )
    session.add(chunk_2023)

    # Seed chunks for 2024 (High/Critical severity supply chain risk)
    chunk_2024 = DocumentChunk(
        report_id=report_2024.id,
        chunk_index=0,
        chunk_text="We face significant disruption to our supply chain which poses an existential threat and risk.",
        token_count=17,
        chunk_metadata={"normalized_section_name": "Risk Factors", "report_id": str(report_2024.id)}
    )
    session.add(chunk_2024)

    session.commit()
    return company.id, report_2023.id, report_2024.id


@pytest.mark.integration
def test_risk_tasks_ingestion_and_evolution(sync_session: Session) -> None:
    company_id, report_2023_id, report_2024_id = _seed_company_and_reports(sync_session)

    # Mock Celery delay so it doesn't fail on Redis connection.
    with patch("app.tasks.ingestion.generate_risk_evolution_task.delay") as mock_delay:
        # 1. Run risk extraction for 2023 report
        res_2023 = extract_risks_task(str(report_2023_id))
        assert res_2023["status"] == "RISK_EXTRACTED_PARTIAL"
        assert res_2023["risks"] >= 1
        mock_delay.assert_called_once()

    # Verify report status is now RISK_EXTRACTING/EXTRACTED_PARTIAL
    report_2023 = sync_session.get(Report, report_2023_id)
    assert report_2023.status in (ReportStatus.RISK_EXTRACTING, ReportStatus.RISK_EXTRACTED)

    # Verify risk factor was created
    rf_2023 = sync_session.query(RiskFactor).filter_by(report_id=report_2023_id).all()
    assert len(rf_2023) >= 1
    supply_chain_rf_2023 = next((r for r in rf_2023 if r.normalized_risk_name == "SUPPLY_CHAIN_RISK"), None)
    assert supply_chain_rf_2023 is not None
    assert supply_chain_rf_2023.severity == "LOW"  # matches "minor"

    # Mock Celery delay again
    with patch("app.tasks.ingestion.generate_risk_evolution_task.delay") as mock_delay:
        # 2. Run risk extraction for 2024 report
        res_2024 = extract_risks_task(str(report_2024_id))
        assert res_2024["status"] == "RISK_EXTRACTED_PARTIAL"
        assert res_2024["risks"] >= 1
        mock_delay.assert_called_once()

    rf_2024 = sync_session.query(RiskFactor).filter_by(report_id=report_2024_id).all()
    assert len(rf_2024) >= 1
    supply_chain_rf_2024 = next((r for r in rf_2024 if r.normalized_risk_name == "SUPPLY_CHAIN_RISK"), None)
    assert supply_chain_rf_2024 is not None
    assert supply_chain_rf_2024.severity == "CRITICAL"  # matches "existential threat"

    # 3. Generate risk evolution for 2024 report (since there is a prior 2023 report)
    res_evol = generate_risk_evolution_task(str(report_2024_id))
    assert res_evol["status"] == "RISKS_READY"
    assert res_evol["evolutions"] >= 1

    # Verify risk evolution record was created
    evolutions = sync_session.query(RiskEvolution).filter_by(company_id=company_id).all()
    assert len(evolutions) >= 1
    # Check that it's ESCALATED_RISK since it went from LOW to CRITICAL
    sc_evol = next((e for e in evolutions if e.evolution_type == "ESCALATED_RISK"), None)
    assert sc_evol is not None
    assert sc_evol.previous_risk_id == supply_chain_rf_2023.id
    assert sc_evol.current_risk_id == supply_chain_rf_2024.id


@pytest.mark.integration
async def test_risks_api_endpoints(api_client: AsyncClient, sync_session: Session) -> None:
    company_id, report_2023_id, report_2024_id = _seed_company_and_reports(sync_session)

    # Ingest and generate evolution (patch celery delay so it doesn't fail on Redis)
    with patch("app.tasks.ingestion.generate_risk_evolution_task.delay"):
        extract_risks_task(str(report_2023_id))
        extract_risks_task(str(report_2024_id))
    generate_risk_evolution_task(str(report_2024_id))

    # Test GET /reports/{report_id}/risks
    resp = await api_client.get(f"{PREFIX}/reports/{report_2024_id}/risks")
    assert resp.status_code == 200
    listing = resp.json()
    assert listing["count"] >= 1
    risk = next((r for r in listing["items"] if r["normalized_risk_name"] == "SUPPLY_CHAIN_RISK"), None)
    assert risk is not None
    assert risk["risk_name"] is not None
    assert risk["severity"] == "CRITICAL"
    assert risk["category"] == "SUPPLY_CHAIN"

    # Test GET /reports/{report_id}/risks/{risk_id}
    risk_id = risk["id"]
    resp_det = await api_client.get(f"{PREFIX}/reports/{report_2024_id}/risks/{risk_id}")
    assert resp_det.status_code == 200
    detail = resp_det.json()
    assert detail["id"] == risk_id
    assert detail["severity"] == "CRITICAL"

    # Test POST /reports/{report_id}/risks/extract
    resp_ext = await api_client.post(f"{PREFIX}/reports/{report_2024_id}/risks/extract")
    assert resp_ext.status_code == 202
    assert resp_ext.json()["task_enqueued"] is True

    # Test GET /companies/{company_id}/risks
    resp_co = await api_client.get(f"{PREFIX}/companies/{company_id}/risks")
    assert resp_co.status_code == 200
    co_risks = resp_co.json()
    assert co_risks["count"] >= 1

    # Test GET /companies/{company_id}/risk-evolution
    resp_evol = await api_client.get(f"{PREFIX}/companies/{company_id}/risk-evolution")
    assert resp_evol.status_code == 200
    evol_listing = resp_evol.json()
    assert evol_listing["count"] >= 1
    assert any(e["evolution_type"] == "ESCALATED_RISK" for e in evol_listing["items"])

    # Test GET /companies/{company_id}/risk-summary
    resp_sum = await api_client.get(f"{PREFIX}/companies/{company_id}/risk-summary")
    assert resp_sum.status_code == 200
    summary = resp_sum.json()
    assert summary["total_risks"] >= 1
    assert summary["by_severity"]["CRITICAL"] >= 1
    assert summary["by_category"]["SUPPLY_CHAIN"] >= 1
    assert summary["evolution_counts"]["ESCALATED_RISK"] >= 1
