"""Data models for tone evolution tracking (Phase 5)."""

from __future__ import annotations

import uuid
from pydantic import BaseModel, Field

from app.models.enums import ToneEvolutionType


class ToneEvolutionCandidate(BaseModel):
    """Temporary tone evolution candidate representing the PoP change."""

    company_id: uuid.UUID
    current_tone_id: uuid.UUID | None = None
    previous_tone_id: uuid.UUID | None = None
    evolution_type: ToneEvolutionType
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    explanation: str

    def key(self) -> str:
        """Deterministic grouping key based on matched IDs."""
        return f"{self.current_tone_id or ''}_{self.previous_tone_id or ''}"


class ExtractedToneEvolution(BaseModel):
    """Validated tone evolution record to be stored in the database."""

    company_id: uuid.UUID
    current_tone_id: uuid.UUID | None = None
    previous_tone_id: uuid.UUID | None = None
    evolution_type: ToneEvolutionType
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    explanation: str
