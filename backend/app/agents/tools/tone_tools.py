"""Tone tools for Agent system (Phase 7).

Provides database query functions to access Management Tone and Tone Evolution data.
"""

from __future__ import annotations

import uuid
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.management_tone import ManagementTone
from app.models.tone_evolution import ToneEvolution


async def get_management_tone(
    db: AsyncSession,
    company_id: uuid.UUID | None = None,
    report_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    """Query and return management tone records filtered by company_id or report_id."""
    stmt = select(ManagementTone)
    if report_id:
        stmt = stmt.where(ManagementTone.report_id == report_id)
    elif company_id:
        stmt = stmt.where(ManagementTone.company_id == company_id)
        
    result = await db.execute(stmt)
    tones = result.scalars().all()
    
    return [
        {
            "id": str(t.id),
            "company_id": str(t.company_id),
            "report_id": str(t.report_id),
            "source_type": t.source_type,
            "sentiment": t.sentiment,
            "confidence_level": t.confidence_level,
            "hedging_score": float(t.hedging_score),
            "positive_score": float(t.positive_score),
            "negative_score": float(t.negative_score),
            "confidence_score": float(t.confidence_score),
        }
        for t in tones
    ]


async def get_tone_evolution(
    db: AsyncSession,
    company_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    """Query and return tone evolution records for a given company."""
    stmt = select(ToneEvolution)
    if company_id:
        stmt = stmt.where(ToneEvolution.company_id == company_id)
        
    result = await db.execute(stmt)
    evolutions = result.scalars().all()
    
    return [
        {
            "id": str(e.id),
            "company_id": str(e.company_id),
            "current_tone_id": str(e.current_tone_id) if e.current_tone_id else None,
            "previous_tone_id": str(e.previous_tone_id) if e.previous_tone_id else None,
            "evolution_type": e.evolution_type,
            "confidence_score": float(e.confidence_score),
            "explanation": e.explanation,
        }
        for e in evolutions
    ]
