"""Confidence level classification helper for management tone analysis (Phase 5)."""

from __future__ import annotations

from app.models.enums import ConfidenceLevel


def classify_confidence_level(
    confidence_phrase_score: float, hedging_phrase_score: float
) -> ConfidenceLevel:
    """Classify confidence level based on confidence and hedging scores.

    - VERY_CONFIDENT: high confidence words, very low hedging
    - CONFIDENT: moderate confidence words, low hedging
    - VERY_CAUTIOUS: high hedging, low confidence words
    - CAUTIOUS: moderate hedging
    """
    if confidence_phrase_score >= 0.15 and hedging_phrase_score <= 0.05:
        return ConfidenceLevel.VERY_CONFIDENT
    if confidence_phrase_score >= 0.05 and hedging_phrase_score <= 0.10:
        return ConfidenceLevel.CONFIDENT
    if hedging_phrase_score >= 0.15 and confidence_phrase_score <= 0.05:
        return ConfidenceLevel.VERY_CAUTIOUS
    if hedging_phrase_score >= 0.05:
        return ConfidenceLevel.CAUTIOUS
    return ConfidenceLevel.CONFIDENT
