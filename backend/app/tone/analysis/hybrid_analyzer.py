"""Hybrid management tone analyzer (Phase 5)."""

from __future__ import annotations

import time
import uuid

from app.core.logging import get_logger
from app.models.enums import Sentiment, ConfidenceLevel
from app.tone.analysis.confidence_scoring import compute_tone_confidence
from app.tone.analysis.models import (
    ExtractedTone,
    ToneCandidate,
    ToneChunkInput,
    ToneExtractionResult,
    ToneExtractionStats,
)
from app.tone.analysis.llm_analyzer import LLMBasedToneAnalyzer
from app.tone.analysis.rule_analyzer import RuleBasedToneAnalyzer
from app.tone.analysis.validators import ToneValidator

log = get_logger(__name__)


class HybridToneAnalyzer:
    """Combines rule-based and LLM-based analysis to reconcile and validate tone."""

    def __init__(
        self,
        *,
        rule_analyzer: RuleBasedToneAnalyzer | None = None,
        llm_analyzer: LLMBasedToneAnalyzer | None = None,
        validator: ToneValidator | None = None,
    ) -> None:
        self.rule = rule_analyzer or RuleBasedToneAnalyzer()
        self.llm = llm_analyzer or LLMBasedToneAnalyzer.from_settings()
        self.validator = validator or ToneValidator()

    def analyze(self, company_id: uuid.UUID, chunks: list[ToneChunkInput]) -> ToneExtractionResult:
        started = time.monotonic()
        stats = ToneExtractionStats(chunks_processed=len(chunks))

        records: list[ExtractedTone] = []

        if not self.llm.enabled:
            stats.llm_errors = 0

        for ch in chunks:
            rule_cand = self.rule.analyze(ch)
            llm_cand = None

            if self.llm.enabled:
                try:
                    llm_cand = self.llm.analyze_chunk(ch)
                    if llm_cand is not None:
                        stats.llm_hits += 1
                except Exception as exc:  # noqa: BLE001
                    stats.llm_errors += 1
                    log.error("tone_extraction.llm_failed", chunk_id=ch.chunk_id, error=str(exc))

            if rule_cand is not None:
                stats.rule_hits += 1

            resolved = self._resolve(rule_cand, llm_cand, stats)
            if resolved is not None:
                # Validate
                vr = self.validator.validate(resolved)
                if not vr.is_valid:
                    stats.validation_failures += 1
                    log.warning(
                        "tone_extraction.validation_failed",
                        chunk_id=ch.chunk_id,
                        errors=vr.errors,
                    )
                    continue

                metadata = dict(resolved.extraction_metadata)
                if vr.warnings:
                    metadata["validation_warnings"] = vr.warnings

                # Convert to ExtractedTone
                source_chunk_uuid = uuid.UUID(resolved.source_chunk_id) if resolved.source_chunk_id else None
                records.append(
                    ExtractedTone(
                        company_id=company_id,
                        source_chunk_id=source_chunk_uuid,
                        source_type=resolved.source_type,
                        sentiment=resolved.sentiment,
                        confidence_level=resolved.confidence_level,
                        hedging_score=resolved.hedging_score,
                        positive_score=resolved.positive_score,
                        negative_score=resolved.negative_score,
                        confidence_score=resolved.confidence_score,
                        extraction_method=resolved.extraction_method,
                        source_text=resolved.source_text,
                        extraction_metadata=metadata,
                    )
                )

        stats.duration_seconds = round(time.monotonic() - started, 3)
        log.info("tone_extraction.run_complete", records=len(records), **stats.as_dict())
        return ToneExtractionResult(tone_records=records, stats=stats)

    def _resolve(
        self,
        r: ToneCandidate | None,
        ll: ToneCandidate | None,
        stats: ToneExtractionStats,
    ) -> ToneCandidate | None:
        if r is not None and ll is not None:
            # Agree?
            sentiment_agree = r.sentiment == ll.sentiment
            confidence_agree = r.confidence_level == ll.confidence_level

            if sentiment_agree and confidence_agree:
                stats.agreements += 1
                conf = compute_tone_confidence("HYBRID_VALIDATED")
                meta = {
                    "rule_sentiment": r.sentiment.value,
                    "llm_sentiment": ll.sentiment.value,
                    "rule_confidence": r.confidence_level.value,
                    "llm_confidence": ll.confidence_level.value,
                    "agreement": True,
                }
                # Average scores for consensus
                return ToneCandidate(
                    source_chunk_id=r.source_chunk_id,
                    source_type=r.source_type,
                    sentiment=r.sentiment,
                    confidence_level=r.confidence_level,
                    hedging_score=round((r.hedging_score + ll.hedging_score) / 2.0, 3),
                    positive_score=round((r.positive_score + ll.positive_score) / 2.0, 3),
                    negative_score=round((r.negative_score + ll.negative_score) / 2.0, 3),
                    confidence_score=conf,
                    source_text=r.source_text,
                    extraction_method="HYBRID_VALIDATED",
                    extraction_metadata=meta,
                )

            # Disagree
            stats.disagreements += 1
            log.warning(
                "tone_extraction.consensus_discrepancy",
                chunk_id=r.source_chunk_id,
                rule_sentiment=r.sentiment,
                llm_sentiment=ll.sentiment,
                rule_confidence=r.confidence_level,
                llm_confidence=ll.confidence_level,
            )
            conf = compute_tone_confidence("RULE_BASED", disagreement=True)
            meta = {
                "rule_sentiment": r.sentiment.value,
                "llm_sentiment": ll.sentiment.value,
                "rule_confidence": r.confidence_level.value,
                "llm_confidence": ll.confidence_level.value,
                "discrepancy": True,
            }
            # Fall back to Rule values
            return ToneCandidate(
                source_chunk_id=r.source_chunk_id,
                source_type=r.source_type,
                sentiment=r.sentiment,
                confidence_level=r.confidence_level,
                hedging_score=r.hedging_score,
                positive_score=r.positive_score,
                negative_score=r.negative_score,
                confidence_score=conf,
                source_text=r.source_text,
                extraction_method="RULE_BASED",
                extraction_metadata=meta,
            )

        if r is not None:
            # Rule only
            conf = compute_tone_confidence("RULE_BASED")
            return ToneCandidate(
                source_chunk_id=r.source_chunk_id,
                source_type=r.source_type,
                sentiment=r.sentiment,
                confidence_level=r.confidence_level,
                hedging_score=r.hedging_score,
                positive_score=r.positive_score,
                negative_score=r.negative_score,
                confidence_score=conf,
                source_text=r.source_text,
                extraction_method="RULE_BASED",
                extraction_metadata={},
            )

        if ll is not None:
            # LLM only
            conf = compute_tone_confidence("LLM_BASED", llm_confidence=ll.confidence_score)
            return ToneCandidate(
                source_chunk_id=ll.source_chunk_id,
                source_type=ll.source_type,
                sentiment=ll.sentiment,
                confidence_level=ll.confidence_level,
                hedging_score=ll.hedging_score,
                positive_score=ll.positive_score,
                negative_score=ll.negative_score,
                confidence_score=conf,
                source_text=ll.source_text,
                extraction_method="LLM_BASED",
                extraction_metadata={},
            )

        return None
