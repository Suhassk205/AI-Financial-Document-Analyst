"""Sentiment classification helper for management tone analysis (Phase 5)."""

from __future__ import annotations

from app.models.enums import Sentiment


def classify_sentiment(positive_score: float, negative_score: float) -> Sentiment:
    """Classify sentiment based on positive and negative score comparison.

    Uses a small threshold tolerance (0.01) to handle floating point noise.
    """
    diff = positive_score - negative_score
    if diff > 0.01:
        return Sentiment.POSITIVE
    if diff < -0.01:
        return Sentiment.NEGATIVE
    return Sentiment.NEUTRAL
