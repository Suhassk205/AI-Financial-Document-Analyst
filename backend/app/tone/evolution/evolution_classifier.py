"""Classification logic for period-over-period tone changes (Phase 5)."""

from __future__ import annotations

from app.models.enums import ToneEvolutionType, Sentiment, ConfidenceLevel
from app.models.management_tone import ManagementTone
from app.tone.evolution.models import ToneEvolutionCandidate

_CONFIDENCE_VALUES = {
    ConfidenceLevel.VERY_CAUTIOUS: 1,
    ConfidenceLevel.CAUTIOUS: 2,
    ConfidenceLevel.CONFIDENT: 3,
    ConfidenceLevel.VERY_CONFIDENT: 4,
}


class ToneEvolutionClassifier:
    """Classifies matched management tone records into PoP evolution transitions."""

    def classify(self, current: ManagementTone, previous: ManagementTone) -> ToneEvolutionCandidate:
        c_sent = Sentiment(current.sentiment)
        p_sent = Sentiment(previous.sentiment)

        # 1. Sentiment changes
        if p_sent == Sentiment.NEGATIVE and c_sent in (Sentiment.NEUTRAL, Sentiment.POSITIVE):
            evolution_type = ToneEvolutionType.MORE_POSITIVE
            explanation = f"Sentiment improved from NEGATIVE to {c_sent.value} in {current.source_type}."
        elif p_sent == Sentiment.NEUTRAL and c_sent == Sentiment.POSITIVE:
            evolution_type = ToneEvolutionType.MORE_POSITIVE
            explanation = f"Sentiment improved from NEUTRAL to POSITIVE in {current.source_type}."
        elif p_sent == Sentiment.POSITIVE and c_sent in (Sentiment.NEUTRAL, Sentiment.NEGATIVE):
            evolution_type = ToneEvolutionType.MORE_NEGATIVE
            explanation = f"Sentiment declined from POSITIVE to {c_sent.value} in {current.source_type}."
        elif p_sent == Sentiment.NEUTRAL and c_sent == Sentiment.NEGATIVE:
            evolution_type = ToneEvolutionType.MORE_NEGATIVE
            explanation = f"Sentiment declined from NEUTRAL to NEGATIVE in {current.source_type}."

        # 2. Confidence level changes (if sentiment is unchanged)
        else:
            c_val = _CONFIDENCE_VALUES.get(ConfidenceLevel(current.confidence_level), 3)
            p_val = _CONFIDENCE_VALUES.get(ConfidenceLevel(previous.confidence_level), 3)

            if c_val > p_val:
                evolution_type = ToneEvolutionType.MORE_CONFIDENT
                explanation = f"Sentiment remained {c_sent.value}, but confidence increased from {previous.confidence_level} to {current.confidence_level}."
            elif c_val < p_val:
                evolution_type = ToneEvolutionType.MORE_CAUTIOUS
                explanation = f"Sentiment remained {c_sent.value}, but confidence decreased from {previous.confidence_level} to {current.confidence_level}."

            # 3. Hedging changes (if sentiment and confidence level are unchanged)
            else:
                hedge_diff = current.hedging_score - previous.hedging_score
                if hedge_diff <= -0.05:
                    evolution_type = ToneEvolutionType.MORE_CONFIDENT
                    explanation = f"Sentiment remained {c_sent.value} and confidence level stayed {current.confidence_level}, but hedging (uncertainty language) decreased from {previous.hedging_score} to {current.hedging_score}."
                elif hedge_diff >= 0.05:
                    evolution_type = ToneEvolutionType.MORE_CAUTIOUS
                    explanation = f"Sentiment remained {c_sent.value} and confidence level stayed {current.confidence_level}, but hedging (uncertainty language) increased from {previous.hedging_score} to {current.hedging_score}."
                else:
                    evolution_type = ToneEvolutionType.UNCHANGED
                    explanation = f"Tone remained unchanged at {c_sent.value} ({current.confidence_level}) with stable hedging."

        # Average confidence of both extractions for evolution confidence score
        confidence_score = round((float(current.confidence_score) + float(previous.confidence_score)) / 2.0, 3)

        return ToneEvolutionCandidate(
            company_id=current.company_id,
            current_tone_id=current.id,
            previous_tone_id=previous.id,
            evolution_type=evolution_type,
            confidence_score=confidence_score,
            explanation=explanation,
        )
