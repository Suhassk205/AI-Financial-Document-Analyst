"""Validation logic for tone evolution candidates (Phase 5)."""

from __future__ import annotations

from pydantic import BaseModel, Field
from app.tone.evolution.models import ToneEvolutionCandidate


class ToneEvolutionValidationResult(BaseModel):
    """Result of tone evolution candidate validation."""

    is_valid: bool
    errors: list[str] = Field(default_factory=list)


class ToneEvolutionValidator:
    """Validates tone evolution candidates."""

    def validate(self, candidate: ToneEvolutionCandidate) -> ToneEvolutionValidationResult:
        errors: list[str] = []

        # Check confidence range
        if not (0.0 <= candidate.confidence_score <= 1.0):
            errors.append(f"confidence_score {candidate.confidence_score} is outside [0.0, 1.0] range")

        # Must have at least one of current or previous tone id
        if candidate.current_tone_id is None and candidate.previous_tone_id is None:
            errors.append("Both current_tone_id and previous_tone_id cannot be null")

        # Check explanation
        if not candidate.explanation or not candidate.explanation.strip():
            errors.append("explanation is empty or contains only whitespace")

        return ToneEvolutionValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
        )
