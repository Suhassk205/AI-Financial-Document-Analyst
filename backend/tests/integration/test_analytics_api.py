"""Integration tests for Phase 3C: metrics + comparisons → analytics engine → DB + APIs."""

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
from app.models.financial_analytics import FinancialAnalytics
from app.models.report import Report
from app.tasks.ingestion import generate_financial_analytics_task

PREFIX = settings.api_v1_prefix


def _report(session: Session, company_id, year: int) -> uuid.UUID:
    r = Report(
        company_id=company_id,
        report_type="10-K",
        year=year,
        original_filename="x.pdf",
        storage_path=f"reports/2026/06/{year}_x.pdf",
        status=ReportStatus.COMPARED,
        total_pages=1,
    )
    session.add(r)
    session.commit()
    return r.id


def _metric(session: Session, report_id, name, value, year, cat="REVENUE"):
    session.add(
        FinancialMetric(
            report_id=report_id,
            metric_name=name,
            normalized_metric_name=name,
            metric_category=cat,
            value=Decimal(str(value)),
            currency="USD",
            unit="ABSOLUTE",
            fiscal_year=year,
            fiscal_quarter=None,
            confidence_score=Decimal("0.9"),
            extraction_method="RULE_BASED",
            source_text="seed",
        )
    )
    session.commit()


def _comparison(session: Session, company_id, metric_id, name, curr, prev, pct=None, abs_val=None):
    session.add(
        MetricComparison(
            metric_id=metric_id,
            company_id=company_id,
            metric_name=name,
            comparison_type="YOY",
            current_period="FY2024",
            previous_period="FY2023",
            current_value=Decimal(str(curr)),
            previous_value=Decimal(str(prev)),
            absolute_change=Decimal(str(abs_val)) if abs_val is not None else None,
            percentage_change=Decimal(str(pct)) if pct is not None else None,
        )
    )
    session.commit()


def _seed(session: Session) -> dict:
    c = Company(name="Beta Corp", ticker="BETA")
    session.add(c)
    session.commit()

    r24 = _report(session, c.id, 2024)
    r23 = _report(session, c.id, 2023)

    # Metrics
    _metric(session, r24, "REVENUE", 1000.0, 2024)
    _metric(session, r24, "GROSS_PROFIT", 600.0, 2024, cat="PROFITABILITY")
    _metric(session, r24, "OPERATING_INCOME", 200.0, 2024, cat="PROFITABILITY")
    _metric(session, r24, "NET_INCOME", 150.0, 2024, cat="PROFITABILITY")
    _metric(session, r24, "TOTAL_DEBT", 200.0, 2024, cat="DEBT")
    _metric(session, r24, "OPERATING_CASH_FLOW", 250.0, 2024, cat="CASH_FLOW")
    _metric(session, r24, "FREE_CASH_FLOW", 200.0, 2024, cat="CASH_FLOW")

    # We need the metric IDs to build comparisons
    m_list = session.query(FinancialMetric).filter(FinancialMetric.report_id == r24).all()
    m_by_name = {m.normalized_metric_name: m for m in m_list}

    # Comparisons
    _comparison(session, c.id, m_by_name["REVENUE"].id, "REVENUE", 1000.0, 800.0, pct=0.25)
    _comparison(session, c.id, m_by_name["NET_INCOME"].id, "NET_INCOME", 150.0, 80.0, pct=0.875)
    _comparison(session, c.id, m_by_name["TOTAL_DEBT"].id, "TOTAL_DEBT", 200.0, 200.0, pct=0.00)
    _comparison(session, c.id, m_by_name["FREE_CASH_FLOW"].id, "FREE_CASH_FLOW", 200.0, 100.0, pct=1.00)

    return {"company": c.id, "r24": r24, "r23": r23}


@pytest.mark.integration
def test_analytics_task_stores_results(sync_session: Session) -> None:
    ids = _seed(sync_session)
    result = generate_financial_analytics_task(str(ids["r24"]))
    
    assert result["status"] == "ANALYTICS_READY"
    assert result["analytics"] > 0

    rows = (
        sync_session.query(FinancialAnalytics)
        .filter(FinancialAnalytics.company_id == ids["company"])
        .all()
    )
    
    # We should have ratios and signals
    ratios = {r.signal_code: r for r in rows if r.classification == "RATIO"}
    signals = {s.signal_code: s for s in rows if s.classification != "RATIO"}

    assert "GROSS_MARGIN" in ratios
    assert ratios["GROSS_MARGIN"].value == Decimal("0.60")

    assert "REVENUE_GROWTH_YOY" in signals
    assert signals["REVENUE_GROWTH_YOY"].severity == "VERY_POSITIVE"

    report = sync_session.get(Report, ids["r24"])
    assert report.status == ReportStatus.ANALYZED


@pytest.mark.integration
async def test_analytics_apis(api_client: AsyncClient, sync_session: Session) -> None:
    ids = _seed(sync_session)
    generate_financial_analytics_task(str(ids["r24"]))

    # 1. Report analytics
    resp = await api_client.get(f"{PREFIX}/reports/{ids['r24']}/analytics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] > 0

    # 2. Company analytics
    resp = await api_client.get(f"{PREFIX}/companies/{ids['company']}/analytics")
    assert resp.status_code == 200
    assert resp.json()["count"] > 0

    # 3. Company signals (excluding ratios)
    resp = await api_client.get(f"{PREFIX}/companies/{ids['company']}/analytics/signals")
    assert resp.status_code == 200
    signals = resp.json()["items"]
    assert len(signals) > 0
    assert all(s["classification"] != "RATIO" for s in signals)

    # 4. Company ratios (excluding signals)
    resp = await api_client.get(f"{PREFIX}/companies/{ids['company']}/analytics/ratios")
    assert resp.status_code == 200
    ratios = resp.json()["items"]
    assert len(ratios) > 0
    assert all(r["classification"] == "RATIO" for r in ratios)

    # 5. Company summary
    resp = await api_client.get(f"{PREFIX}/companies/{ids['company']}/analytics-summary")
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["total"] > 0
    assert "PROFITABILITY" in summary["by_type"]
    assert "VERY_POSITIVE" in summary["by_severity"]


@pytest.mark.integration
async def test_analytics_generate_endpoint(api_client: AsyncClient, sync_session: Session) -> None:
    ids = _seed(sync_session)
    resp = await api_client.post(f"{PREFIX}/reports/{ids['r24']}/analytics/generate")
    assert resp.status_code == 202
    assert resp.json()["task_enqueued"] is True


@pytest.mark.integration
async def test_analytics_404s(api_client: AsyncClient) -> None:
    unknown = str(uuid.uuid4())
    assert (await api_client.get(f"{PREFIX}/reports/{unknown}/analytics")).status_code == 404
    assert (await api_client.get(f"{PREFIX}/companies/{unknown}/analytics")).status_code == 404
    assert (await api_client.get(f"{PREFIX}/companies/{unknown}/analytics-summary")).status_code == 404


@pytest.mark.integration
def test_analytics_idempotency(sync_session: Session) -> None:
    ids = _seed(sync_session)
    first_res = generate_financial_analytics_task(str(ids["r24"]))
    second_res = generate_financial_analytics_task(str(ids["r24"]))
    
    assert first_res["analytics"] == second_res["analytics"]
    
    count = (
        sync_session.query(FinancialAnalytics)
        .filter(FinancialAnalytics.company_id == ids["company"])
        .count()
    )
    assert count == first_res["analytics"]
