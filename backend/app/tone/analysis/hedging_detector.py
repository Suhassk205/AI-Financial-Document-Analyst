"""Hedging detector helper for management tone analysis (Phase 5)."""

from __future__ import annotations

from app.tone.taxonomy.normalization import count_phrase_occurrences, split_sentences
from app.tone.taxonomy.hedging_phrases import HEDGING_PHRASES


def detect_hedging_strength(text: str) -> float:
    """Score hedging strength (0.0 to 1.0) based on hedging phrase frequency."""
    if not text:
        return 0.0

    sentences = split_sentences(text)
    num_sentences = max(1, len(sentences))

    count = count_phrase_occurrences(text, HEDGING_PHRASES)
    score = count / num_sentences
    return max(0.0, min(1.0, score))
