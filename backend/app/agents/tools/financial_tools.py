"""Financial tools for Agent system (Phase 7).

Provides database query functions to access Financial Metrics, Metric Comparisons, and Financial Analytics.
"""

from __future__ import annotations

import uuid
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.financial_metric import FinancialMetric
from app.models.metric_comparison import MetricComparison
from app.models.financial_analytics import FinancialAnalytics
from app.models.report import Report


async def get_financial_metrics(
    db: AsyncSession,
    company_id: uuid.UUID | None = None,
    report_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    """Query and return financial metrics filtered by company_id or report_id."""
    stmt = select(FinancialMetric)
    if report_id:
        stmt = stmt.where(FinancialMetric.report_id == report_id)
    elif company_id:
        stmt = stmt.join(Report).where(Report.company_id == company_id)
    
    result = await db.execute(stmt)
    metrics = result.scalars().all()
    
    return [
        {
            "id": str(m.id),
            "report_id": str(m.report_id),
            "metric_name": m.metric_name,
            "normalized_metric_name": m.normalized_metric_name,
            "metric_category": m.metric_category,
            "value": float(m.value),
            "currency": m.currency,
            "unit": m.unit,
            "fiscal_year": m.fiscal_year,
            "fiscal_quarter": m.fiscal_quarter,
            "confidence_score": float(m.confidence_score),
            "source_text": m.source_text,
        }
        for m in metrics
    ]


async def get_metric_comparisons(
    db: AsyncSession,
    company_id: uuid.UUID | None = None,
    report_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    """Query and return metric comparisons filtered by company_id or report_id."""
    stmt = select(MetricComparison)
    if report_id:
        stmt = stmt.where(
            (MetricComparison.current_report_id == report_id) |
            (MetricComparison.previous_report_id == report_id)
        )
    elif company_id:
        stmt = stmt.where(MetricComparison.company_id == company_id)
        
    result = await db.execute(stmt)
    comparisons = result.scalars().all()
    
    return [
        {
            "id": str(c.id),
            "company_id": str(c.company_id),
            "metric_name": c.metric_name,
            "current_value": float(c.current_value) if c.current_value is not None else None,
            "previous_value": float(c.previous_value) if c.previous_value is not None else None,
            "absolute_change": float(c.absolute_change) if c.absolute_change is not None else None,
            "percentage_change": float(c.percentage_change) if c.percentage_change is not None else None,
            "comparison_type": c.comparison_type,
            "current_period": c.current_period,
            "previous_period": c.previous_period,
        }
        for c in comparisons
    ]


async def get_financial_analytics(
    db: AsyncSession,
    company_id: uuid.UUID | None = None,
    report_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    """Query and return financial analytics/ratios/signals filtered by company_id or report_id."""
    stmt = select(FinancialAnalytics)
    if report_id:
        stmt = stmt.where(FinancialAnalytics.report_id == report_id)
    elif company_id:
        stmt = stmt.join(Report).where(Report.company_id == company_id)
        
    result = await db.execute(stmt)
    analytics = result.scalars().all()
    
    return [
        {
            "id": str(a.id),
            "report_id": str(a.report_id),
            "ratio_name": a.ratio_name,
            "ratio_value": float(a.ratio_value) if a.ratio_value is not None else None,
            "category": a.category,
            "fiscal_year": a.fiscal_year,
            "fiscal_quarter": a.fiscal_quarter,
            "signals": a.signals or {},
            "calculation_metadata": a.calculation_metadata or {},
        }
        for a in analytics
    ]
