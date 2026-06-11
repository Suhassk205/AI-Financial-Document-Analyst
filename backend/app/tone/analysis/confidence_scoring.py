"""Confidence score calculation for tone extractions (Phase 5)."""

from __future__ import annotations


def compute_tone_confidence(
    method: str,
    *,
    llm_confidence: float | None = None,
    disagreement: bool = False,
) -> float:
    """Calculate extraction confidence score based on derivation method and consensus.

    - HYBRID_VALIDATED: 0.95 (agreed upon by rule and LLM)
    - RULE_BASED (with discrepancy): 0.50 (low confidence fallback)
    - RULE_BASED (no LLM run/no discrepancy): 0.70 (standard rule confidence)
    - LLM_BASED: uses LLM's own self-reported confidence, defaulting to 0.80.
    """
    if method == "HYBRID_VALIDATED":
        return 0.95
    if method == "RULE_BASED":
        return 0.50 if disagreement else 0.70
    if method == "LLM_BASED":
        if llm_confidence is not None:
            return max(0.0, min(1.0, llm_confidence))
        return 0.80
    return 0.60
