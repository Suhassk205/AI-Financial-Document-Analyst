"""Validation logic for extracted tone candidates (Phase 5)."""

from __future__ import annotations

from pydantic import BaseModel, Field
from app.tone.analysis.models import ToneCandidate


class ToneValidationResult(BaseModel):
    """Result of tone candidate validation."""

    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ToneValidator:
    """Validates extracted tone candidate fields and constraints."""

    def validate(self, candidate: ToneCandidate) -> ToneValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        # Validate score ranges
        for score_name in ("hedging_score", "positive_score", "negative_score", "confidence_score"):
            val = getattr(candidate, score_name)
            if not (0.0 <= val <= 1.0):
                errors.append(f"{score_name} value {val} is outside [0.0, 1.0] range")

        # Check source text
        if not candidate.source_text or not candidate.source_text.strip():
            errors.append("source_text is empty or contains only whitespace")

        # Check source type
        if not candidate.source_type or not candidate.source_type.strip():
            errors.append("source_type is empty or contains only whitespace")

        # Soft validation warning if positive and negative scores are identical
        if candidate.positive_score > 0 and candidate.positive_score == candidate.negative_score:
            warnings.append("positive_score and negative_score are exactly equal and non-zero")

        return ToneValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )
