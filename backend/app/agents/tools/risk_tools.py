"""Risk tools for Agent system (Phase 7).

Provides database query functions to access Risk Factors and Risk Evolution data.
"""

from __future__ import annotations

import uuid
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.risk_factor import RiskFactor
from app.models.risk_evolution import RiskEvolution


async def get_risk_factors(
    db: AsyncSession,
    company_id: uuid.UUID | None = None,
    report_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    """Query and return risk factors filtered by company_id or report_id."""
    stmt = select(RiskFactor)
    if report_id:
        stmt = stmt.where(RiskFactor.report_id == report_id)
    elif company_id:
        stmt = stmt.where(RiskFactor.company_id == company_id)
        
    result = await db.execute(stmt)
    risks = result.scalars().all()
    
    return [
        {
            "id": str(r.id),
            "company_id": str(r.company_id),
            "report_id": str(r.report_id),
            "risk_name": r.risk_name,
            "normalized_risk_name": r.normalized_risk_name,
            "risk_description": r.risk_description,
            "category": r.category,
            "severity": r.severity,
            "confidence_score": float(r.confidence_score),
            "source_text": r.source_text,
        }
        for r in risks
    ]


async def get_risk_evolution(
    db: AsyncSession,
    company_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    """Query and return risk evolution records for a given company."""
    stmt = select(RiskEvolution)
    if company_id:
        stmt = stmt.where(RiskEvolution.company_id == company_id)
        
    result = await db.execute(stmt)
    evolutions = result.scalars().all()
    
    return [
        {
            "id": str(e.id),
            "company_id": str(e.company_id),
            "current_risk_id": str(e.current_risk_id) if e.current_risk_id else None,
            "previous_risk_id": str(e.previous_risk_id) if e.previous_risk_id else None,
            "evolution_type": e.evolution_type,
            "confidence_score": float(e.confidence_score),
            "explanation": e.explanation,
        }
        for e in evolutions
    ]
