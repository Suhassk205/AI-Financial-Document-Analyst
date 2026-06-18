"""Integration tests for Phase 3A: chunk → extraction → validation → DB + APIs.

Runs the real extraction task (rule-only — no Gemini key in tests) against a live
PostgreSQL, then inspects the metrics via the APIs.
"""

from __future__ import annotations

import uuid

import pytest
from app.core.config import settings
from app.models.document_chunk import DocumentChunk
from app.models.enums import ReportStatus
from app.models.financial_metric import FinancialMetric
from app.models.report import Report
from app.tasks.ingestion import extract_financial_metrics_task
from httpx import AsyncClient
from sqlalchemy.orm import Session

PREFIX = settings.api_v1_prefix

_CHUNKS = [
    ("Income Statement",
     "Total revenue was $96.7 billion in fiscal 2024. Net income was $5,123 million. "
     "Operating margin was 28.5%."),
    ("Cash Flow Statement",
     "Net cash provided by operating activities was $12.4 billion. Capital expenditures "
     "were $3.1 billion. Free cash flow was $9.3 billion."),
    ("MD&A", "Adjusted EBITDA was $18.2 billion for the year."),
    ("Legal Proceedings", "We are party to various legal proceedings in the ordinary course."),
]


def _seed(session: Session) -> uuid.UUID:
    report = Report(
        report_type="10-K", year=2024, original_filename="x.pdf",
        storage_path="reports/2026/06/x.pdf", status=ReportStatus.CHUNKED, total_pages=1,
    )
    session.add(report)
    session.commit()
    for idx, (section, text) in enumerate(_CHUNKS):
        session.add(
            DocumentChunk(
                report_id=report.id, chunk_index=idx, chunk_text=text,
                token_count=len(text.split()),
                chunk_metadata={"normalized_section_name": section, "report_id": str(report.id)},
            )
        )
    session.commit()
    return report.id


@pytest.mark.integration
def test_extraction_task_stores_metrics(sync_session: Session) -> None:
    report_id = _seed(sync_session)
    result = extract_financial_metrics_task(str(report_id))
    assert result["status"] == "METRICS_READY"
    assert result["metrics"] >= 6

    rows = (
        sync_session.query(FinancialMetric)
        .filter(FinancialMetric.report_id == report_id)
        .all()
    )
    names = {m.normalized_metric_name for m in rows}
    assert {"REVENUE", "NET_INCOME", "OPERATING_MARGIN", "OPERATING_CASH_FLOW",
            "CAPEX", "FREE_CASH_FLOW", "EBITDA"} <= names
    # source traceability + determinism
    for m in rows:
        assert m.source_chunk_id is not None
        assert m.source_text
        assert m.extraction_method == "RULE_BASED"   # LLM disabled in tests
        assert m.fiscal_year == 2024
    rev = next(m for m in rows if m.normalized_metric_name == "REVENUE")
    assert float(rev.value) == 96700000000.0 and rev.unit == "BILLION" and rev.currency == "USD"
    margin = next(m for m in rows if m.normalized_metric_name == "OPERATING_MARGIN")
    assert float(margin.value) == 28.5 and margin.unit == "PERCENT"

    sync_session.refresh(sync_session.get(Report, report_id))
    assert sync_session.get(Report, report_id).status == ReportStatus.EXTRACTED


@pytest.mark.integration
async def test_metrics_apis(api_client: AsyncClient, sync_session: Session) -> None:
    report_id = _seed(sync_session)
    extract_financial_metrics_task(str(report_id))

    listing = (await api_client.get(f"{PREFIX}/reports/{report_id}/metrics")).json()
    assert listing["count"] >= 6
    first = listing["items"][0]
    assert {"normalized_metric_name", "value", "unit", "confidence_score",
            "extraction_method", "source_text", "source_chunk_id"} <= set(first)

    # category filter
    margins = (
        await api_client.get(f"{PREFIX}/reports/{report_id}/metrics?category=MARGINS")
    ).json()
    assert all(m["metric_category"] == "MARGINS" for m in margins["items"])
    assert margins["count"] >= 1

    # summary
    summary = (await api_client.get(f"{PREFIX}/reports/{report_id}/metrics/summary")).json()
    assert summary["total"] >= 6
    assert summary["by_method"]["RULE_BASED"] >= 6
    assert summary["by_category"].get("REVENUE", 0) >= 1
    assert 0.0 < summary["avg_confidence"] <= 1.0

    # detail
    metric_id = listing["items"][0]["id"]
    detail = (await api_client.get(f"{PREFIX}/reports/{report_id}/metrics/{metric_id}")).json()
    assert detail["id"] == metric_id


@pytest.mark.integration
async def test_extract_endpoint_enqueues(api_client: AsyncClient, sync_session: Session) -> None:
    report_id = _seed(sync_session)
    resp = await api_client.post(f"{PREFIX}/reports/{report_id}/metrics/extract")
    assert resp.status_code == 202
    assert resp.json()["task_enqueued"] is True


@pytest.mark.integration
async def test_metrics_404_for_unknown_report(api_client: AsyncClient) -> None:
    unknown = "00000000-0000-0000-0000-000000000000"
    assert (await api_client.get(f"{PREFIX}/reports/{unknown}/metrics")).status_code == 404
    assert (await api_client.get(f"{PREFIX}/reports/{unknown}/metrics/summary")).status_code == 404


@pytest.mark.integration
async def test_extraction_is_idempotent(sync_session: Session) -> None:
    report_id = _seed(sync_session)
    first = extract_financial_metrics_task(str(report_id))["metrics"]
    second = extract_financial_metrics_task(str(report_id))["metrics"]
    assert first == second
    count = (
        sync_session.query(FinancialMetric)
        .filter(FinancialMetric.report_id == report_id)
        .count()
    )
    assert count == second
