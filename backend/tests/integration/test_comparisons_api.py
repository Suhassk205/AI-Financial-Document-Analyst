"""Integration tests for Phase 3B: metrics → comparison engine → DB + APIs.

Seeds a company with two annual reports + metrics, runs the real comparison task
(deterministic, no LLM) against a live PostgreSQL, and inspects via the APIs.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.company import Company
from app.models.enums import ReportStatus
from app.models.financial_metric import FinancialMetric
from app.models.metric_comparison import MetricComparison
from app.models.report import Report
from app.tasks.ingestion import generate_metric_comparisons_task

PREFIX = settings.api_v1_prefix


def _report(session: Session, company_id, year: int) -> uuid.UUID:
    r = Report(
        company_id=company_id, report_type="10-K", year=year, original_filename="x.pdf",
        storage_path="reports/2026/06/x.pdf", status=ReportStatus.EXTRACTED, total_pages=1,
    )
    session.add(r)
    session.commit()
    return r.id


def _metric(session: Session, report_id, name, value, year, cat="REVENUE"):
    session.add(
        FinancialMetric(
            report_id=report_id, metric_name=name, normalized_metric_name=name,
            metric_category=cat, value=Decimal(str(value)), currency="USD", unit="ABSOLUTE",
            fiscal_year=year, fiscal_quarter=None, confidence_score=Decimal("0.9"),
            extraction_method="RULE_BASED", source_text="seed",
        )
    )
    session.commit()


def _seed(session: Session) -> dict:
    c = Company(name="Acme", ticker="ACME")
    session.add(c)
    session.commit()
    r24 = _report(session, c.id, 2024)
    r23 = _report(session, c.id, 2023)
    _metric(session, r24, "REVENUE", 96700000000, 2024)
    _metric(session, r24, "NET_INCOME", 5000000000, 2024, cat="PROFITABILITY")
    _metric(session, r24, "FREE_CASH_FLOW", 5000000000, 2024, cat="CASH_FLOW")
    _metric(session, r23, "REVENUE", 81500000000, 2023)
    _metric(session, r23, "NET_INCOME", -1000000000, 2023, cat="PROFITABILITY")
    _metric(session, r23, "FREE_CASH_FLOW", 0, 2023, cat="CASH_FLOW")
    return {"company": c.id, "r24": r24, "r23": r23}


@pytest.mark.integration
def test_comparison_task_stores_results(sync_session: Session) -> None:
    ids = _seed(sync_session)
    result = generate_metric_comparisons_task(str(ids["r24"]))
    assert result["status"] == "COMPARISON_READY"
    assert result["comparisons"] == 3      # REVENUE, NET_INCOME, FREE_CASH_FLOW (YoY)

    rows = (
        sync_session.query(MetricComparison)
        .filter(MetricComparison.company_id == ids["company"])
        .all()
    )
    by = {r.metric_name: r for r in rows}
    assert by["REVENUE"].comparison_type == "YOY"
    assert by["REVENUE"].absolute_change == Decimal("15200000000")
    assert by["REVENUE"].percentage_change == Decimal("18.65")
    assert by["REVENUE"].previous_period == "FY2023" and by["REVENUE"].current_period == "FY2024"
    # division by zero → NULL percentage, absolute still computed
    assert by["FREE_CASH_FLOW"].percentage_change is None
    assert by["FREE_CASH_FLOW"].absolute_change == Decimal("5000000000")
    # negative base → computed with literal formula
    assert by["NET_INCOME"].percentage_change == Decimal("-600.00")

    sync_session.refresh(sync_session.get(Report, ids["r24"]))
    assert sync_session.get(Report, ids["r24"]).status == ReportStatus.COMPARED


@pytest.mark.integration
async def test_comparison_apis(api_client: AsyncClient, sync_session: Session) -> None:
    ids = _seed(sync_session)
    generate_metric_comparisons_task(str(ids["r24"]))

    rep = (await api_client.get(f"{PREFIX}/reports/{ids['r24']}/comparisons")).json()
    assert rep["count"] == 3

    comp = (await api_client.get(f"{PREFIX}/companies/{ids['company']}/comparisons")).json()
    assert comp["count"] == 3
    rev = next(c for c in comp["items"] if c["metric_name"] == "REVENUE")
    assert rev["percentage_change"] == 18.65 and rev["comparison_type"] == "YOY"

    yoy = (
        await api_client.get(f"{PREFIX}/companies/{ids['company']}/comparisons?comparison_type=YOY")
    ).json()
    assert yoy["count"] == 3 and all(c["comparison_type"] == "YOY" for c in yoy["items"])

    one = (
        await api_client.get(f"{PREFIX}/companies/{ids['company']}/comparisons/REVENUE")
    ).json()
    assert one["count"] == 1 and one["items"][0]["metric_name"] == "REVENUE"

    summary = (
        await api_client.get(f"{PREFIX}/companies/{ids['company']}/comparison-summary")
    ).json()
    assert summary["total"] == 3
    assert summary["by_type"]["YOY"] == 3
    assert summary["by_metric"]["REVENUE"] == 1


@pytest.mark.integration
async def test_generate_endpoint_enqueues(api_client: AsyncClient, sync_session: Session) -> None:
    ids = _seed(sync_session)
    resp = await api_client.post(f"{PREFIX}/reports/{ids['r24']}/comparisons/generate")
    assert resp.status_code == 202
    assert resp.json()["task_enqueued"] is True


@pytest.mark.integration
async def test_404s(api_client: AsyncClient) -> None:
    unknown = "00000000-0000-0000-0000-000000000000"
    assert (await api_client.get(f"{PREFIX}/reports/{unknown}/comparisons")).status_code == 404
    assert (await api_client.get(f"{PREFIX}/companies/{unknown}/comparisons")).status_code == 404
    assert (
        await api_client.get(f"{PREFIX}/companies/{unknown}/comparison-summary")
    ).status_code == 404


@pytest.mark.integration
def test_idempotent(sync_session: Session) -> None:
    ids = _seed(sync_session)
    first = generate_metric_comparisons_task(str(ids["r24"]))["comparisons"]
    second = generate_metric_comparisons_task(str(ids["r24"]))["comparisons"]
    assert first == second == 3
    count = (
        sync_session.query(MetricComparison)
        .filter(MetricComparison.company_id == ids["company"])
        .count()
    )
    assert count == 3


@pytest.mark.integration
def test_no_company_yields_no_comparisons(sync_session: Session) -> None:
    r = Report(
        company_id=None, report_type="10-K", year=2024, original_filename="x.pdf",
        storage_path="p", status=ReportStatus.EXTRACTED,
    )
    sync_session.add(r)
    sync_session.commit()
    result = generate_metric_comparisons_task(str(r.id))
    assert result["status"] == "COMPARISON_READY" and result["comparisons"] == 0
