"""Unit tests for Phase 5 Tone Evolution Engine."""

from __future__ import annotations

import uuid
import pytest

from app.models.enums import Sentiment, ConfidenceLevel, ToneEvolutionType
from app.models.management_tone import ManagementTone
from app.tone.evolution.tone_matcher import ToneMatcher
from app.tone.evolution.evolution_classifier import ToneEvolutionClassifier
from app.tone.evolution.evolution_service import ToneEvolutionService


def test_tone_matcher_matches_by_source_type() -> None:
    company_id = uuid.uuid4()
    report_2023_id = uuid.uuid4()
    report_2024_id = uuid.uuid4()

    current_tones = [
        ManagementTone(
            id=uuid.uuid4(),
            company_id=company_id,
            report_id=report_2024_id,
            source_type="Management Commentary",
            sentiment="POSITIVE",
            confidence_level="VERY_CONFIDENT",
            hedging_score=0.1,
            positive_score=0.8,
            negative_score=0.05,
            confidence_score=0.9,
            extraction_method="RULE_BASED",
            source_text="Delivered exceptional performance."
        ),
        ManagementTone(
            id=uuid.uuid4(),
            company_id=company_id,
            report_id=report_2024_id,
            source_type="Outlook",
            sentiment="NEUTRAL",
            confidence_level="CONFIDENT",
            hedging_score=0.2,
            positive_score=0.4,
            negative_score=0.1,
            confidence_score=0.7,
            extraction_method="RULE_BASED",
            source_text="Outlook is stable."
        )
    ]

    prior_tones = [
        ManagementTone(
            id=uuid.uuid4(),
            company_id=company_id,
            report_id=report_2023_id,
            source_type="Management Commentary",
            sentiment="NEGATIVE",
            confidence_level="CAUTIOUS",
            hedging_score=0.4,
            positive_score=0.1,
            negative_score=0.6,
            confidence_score=0.3,
            extraction_method="RULE_BASED",
            source_text="We expect significant headwinds."
        )
    ]

    matches = ToneMatcher().match(current_tones, prior_tones)
    assert len(matches) == 2

    # Check the matched record
    commentary_match = next(m for m in matches if (m[0] and m[0].source_type == "Management Commentary") or (m[1] and m[1].source_type == "Management Commentary"))
    assert commentary_match[0] is not None
    assert commentary_match[1] is not None
    assert commentary_match[1].sentiment == "NEGATIVE"

    # Check the unmatched outlook record (prior is None)
    outlook_match = next(m for m in matches if (m[0] and m[0].source_type == "Outlook") or (m[1] and m[1].source_type == "Outlook"))
    assert outlook_match[0] is not None
    assert outlook_match[1] is None


def test_evolution_classifier_rules() -> None:
    company_id = uuid.uuid4()
    classifier = ToneEvolutionClassifier()

    # Setup mock ManagementTone objects
    def create_tone(sentiment: Sentiment, confidence: ConfidenceLevel, hedging: float, conf_score: float) -> ManagementTone:
        return ManagementTone(
            id=uuid.uuid4(),
            company_id=company_id,
            report_id=uuid.uuid4(),
            source_type="Management Commentary",
            sentiment=sentiment.value,
            confidence_level=confidence.value,
            hedging_score=hedging,
            positive_score=0.5,
            negative_score=0.1,
            confidence_score=conf_score,
            extraction_method="RULE_BASED",
            source_text="A chunk of source text."
        )

    # More Positive: Negative -> Positive
    cand = classifier.classify(
        create_tone(Sentiment.POSITIVE, ConfidenceLevel.CONFIDENT, 0.2, 0.8),
        create_tone(Sentiment.NEGATIVE, ConfidenceLevel.CONFIDENT, 0.2, 0.8)
    )
    assert cand.evolution_type == ToneEvolutionType.MORE_POSITIVE
    assert cand.confidence_score == 0.8
    assert "improved from NEGATIVE to POSITIVE" in cand.explanation

    # More Negative: Positive -> Negative
    cand = classifier.classify(
        create_tone(Sentiment.NEGATIVE, ConfidenceLevel.CONFIDENT, 0.2, 0.8),
        create_tone(Sentiment.POSITIVE, ConfidenceLevel.CONFIDENT, 0.2, 0.8)
    )
    assert cand.evolution_type == ToneEvolutionType.MORE_NEGATIVE

    # More Confident: Cautious -> Very Confident (same sentiment)
    cand = classifier.classify(
        create_tone(Sentiment.NEUTRAL, ConfidenceLevel.VERY_CONFIDENT, 0.2, 0.9),
        create_tone(Sentiment.NEUTRAL, ConfidenceLevel.CAUTIOUS, 0.2, 0.3)
    )
    assert cand.evolution_type == ToneEvolutionType.MORE_CONFIDENT
    assert cand.confidence_score == 0.6

    # Less Confident / More Cautious: Very Confident -> Cautious (same sentiment)
    cand = classifier.classify(
        create_tone(Sentiment.NEUTRAL, ConfidenceLevel.CAUTIOUS, 0.2, 0.3),
        create_tone(Sentiment.NEUTRAL, ConfidenceLevel.VERY_CONFIDENT, 0.2, 0.9)
    )
    assert cand.evolution_type == ToneEvolutionType.MORE_CAUTIOUS
    assert cand.confidence_score == 0.6


def test_tone_evolution_service() -> None:
    company_id = uuid.uuid4()
    report_2023_id = uuid.uuid4()
    report_2024_id = uuid.uuid4()

    t_2023 = ManagementTone(
        id=uuid.uuid4(),
        company_id=company_id,
        report_id=report_2023_id,
        source_type="Management Commentary",
        sentiment="NEGATIVE",
        confidence_level="CAUTIOUS",
        hedging_score=0.4,
        positive_score=0.1,
        negative_score=0.6,
        confidence_score=0.3,
        extraction_method="RULE_BASED",
        source_text="Significant headwinds."
    )

    t_2024 = ManagementTone(
        id=uuid.uuid4(),
        company_id=company_id,
        report_id=report_2024_id,
        source_type="Management Commentary",
        sentiment="POSITIVE",
        confidence_level="VERY_CONFIDENT",
        hedging_score=0.1,
        positive_score=0.8,
        negative_score=0.05,
        confidence_score=0.9,
        extraction_method="RULE_BASED",
        source_text="Delivered exceptional performance."
    )

    evolutions = ToneEvolutionService().generate_evolution(
        company_id=company_id,
        current_records=[t_2024],
        previous_records=[t_2023]
    )

    assert len(evolutions) == 1
    ev = evolutions[0]
    assert ev.company_id == company_id
    assert ev.current_tone_id == t_2024.id
    assert ev.previous_tone_id == t_2023.id
    assert ev.evolution_type == ToneEvolutionType.MORE_POSITIVE
