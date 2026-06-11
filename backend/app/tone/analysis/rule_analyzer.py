"""Rule-based management tone analyzer (Phase 5)."""

from __future__ import annotations

from app.tone.analysis.models import ToneCandidate, ToneChunkInput
from app.tone.taxonomy.normalization import count_phrase_occurrences, split_sentences
from app.tone.taxonomy.positive_phrases import POSITIVE_PHRASES
from app.tone.taxonomy.negative_phrases import NEGATIVE_PHRASES
from app.tone.taxonomy.confidence_phrases import CONFIDENCE_PHRASES
from app.tone.taxonomy.hedging_phrases import HEDGING_PHRASES
from app.tone.analysis.sentiment_classifier import classify_sentiment
from app.tone.analysis.confidence_classifier import classify_confidence_level
from app.tone.analysis.confidence_scoring import compute_tone_confidence


class RuleBasedToneAnalyzer:
    """Analyzes tone deterministically using phrase-frequency taxonomies."""

    def analyze(self, chunk: ToneChunkInput) -> ToneCandidate | None:
        text = chunk.text
        if not text or not text.strip():
            return None

        sentences = split_sentences(text)
        num_sentences = max(1, len(sentences))

        pos_count = count_phrase_occurrences(text, POSITIVE_PHRASES)
        neg_count = count_phrase_occurrences(text, NEGATIVE_PHRASES)
        conf_count = count_phrase_occurrences(text, CONFIDENCE_PHRASES)
        hedge_count = count_phrase_occurrences(text, HEDGING_PHRASES)

        positive_score = min(1.0, pos_count / num_sentences)
        negative_score = min(1.0, neg_count / num_sentences)
        confidence_phrase_score = min(1.0, conf_count / num_sentences)
        hedging_score = min(1.0, hedge_count / num_sentences)

        sentiment = classify_sentiment(positive_score, negative_score)
        confidence_level = classify_confidence_level(confidence_phrase_score, hedging_score)

        # Baseline confidence score for deterministic rule based
        confidence_score = compute_tone_confidence("RULE_BASED")

        source_type = chunk.normalized_section_name or "Management Commentary"

        return ToneCandidate(
            source_chunk_id=chunk.chunk_id,
            source_type=source_type,
            sentiment=sentiment,
            confidence_level=confidence_level,
            hedging_score=hedging_score,
            positive_score=positive_score,
            negative_score=negative_score,
            confidence_score=confidence_score,
            source_text=text[:300].strip(),
            extraction_method="RULE_BASED",
            extraction_metadata={
                "sentence_count": len(sentences),
                "positive_phrase_count": pos_count,
                "negative_phrase_count": neg_count,
                "confidence_phrase_count": conf_count,
                "hedging_phrase_count": hedge_count,
            },
        )
