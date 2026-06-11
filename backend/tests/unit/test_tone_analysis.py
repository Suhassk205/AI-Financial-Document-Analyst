"""Unit tests for the management tone analysis and evolution frameworks (Phase 5)."""

from __future__ import annotations

import pytest
import uuid

from app.models.enums import Sentiment, ConfidenceLevel, ToneEvolutionType
from app.tone.analysis.models import ToneChunkInput
from app.tone.analysis.sentiment_classifier import classify_sentiment
from app.tone.analysis.confidence_classifier import classify_confidence_level
from app.tone.analysis.hedging_detector import detect_hedging_strength
from app.tone.analysis.rule_analyzer import RuleBasedToneAnalyzer
from app.tone.analysis.hybrid_analyzer import HybridToneAnalyzer
from app.tone.analysis.evaluation import ToneAnalysisEvaluator, load_gold_dataset as load_analysis_gold
from app.tone.evolution.evolution_classifier import ToneEvolutionClassifier
from app.tone.evolution.evolution_service import ToneEvolutionService
from app.tone.evolution.evaluation import ToneEvolutionEvaluator, load_gold_dataset as load_evolution_gold
from app.models.management_tone import ManagementTone


@pytest.mark.unit
def test_sentiment_classifier_rule_based() -> None:
    # Positive
    sentiment1 = classify_sentiment(0.8, 0.1)
    assert sentiment1 == Sentiment.POSITIVE

    # Negative
    sentiment2 = classify_sentiment(0.1, 0.8)
    assert sentiment2 == Sentiment.NEGATIVE

    # Neutral
    sentiment3 = classify_sentiment(0.4, 0.4)
    assert sentiment3 == Sentiment.NEUTRAL


@pytest.mark.unit
def test_confidence_classifier_rule_based() -> None:
    # Very Confident
    level1 = classify_confidence_level(0.20, 0.02)
    assert level1 == ConfidenceLevel.VERY_CONFIDENT

    # Cautious
    level2 = classify_confidence_level(0.01, 0.20)
    assert level2 in (ConfidenceLevel.CAUTIOUS, ConfidenceLevel.VERY_CAUTIOUS)


@pytest.mark.unit
def test_hedging_detector() -> None:
    # High hedging
    score1 = detect_hedging_strength("It might possibly happen subject to changes.")
    assert score1 > 0.0

    # Low/No hedging
    score2 = detect_hedging_strength("")
    assert score2 == 0.0


@pytest.mark.unit
def test_rule_based_tone_analyzer() -> None:
    analyzer = RuleBasedToneAnalyzer()
    chunk = ToneChunkInput(
        chunk_id="00000000-0000-0000-0000-000000000001",
        text="Our company delivered exceptional performance. We expect continued growth.",
        normalized_section_name="CEO Commentary",
        fiscal_year=2026,
        fiscal_quarter=1,
    )
    rec = analyzer.analyze(chunk)
    assert rec is not None
    assert rec.sentiment == Sentiment.POSITIVE
    assert rec.confidence_level == ConfidenceLevel.VERY_CONFIDENT
    assert rec.positive_score > 0.0
    assert rec.negative_score == 0.0


@pytest.mark.unit
def test_tone_evolution_classifier() -> None:
    classifier = ToneEvolutionClassifier()
    company_id = uuid.uuid4()
    
    # POSITIVE to NEGATIVE -> MORE_NEGATIVE
    t1 = classifier.classify(
        ManagementTone(
            id=uuid.uuid4(),
            company_id=company_id,
            sentiment=Sentiment.NEGATIVE,
            confidence_level=ConfidenceLevel.CAUTIOUS,
            hedging_score=0.7,
            positive_score=0.1,
            negative_score=0.7,
            confidence_score=0.8,
            source_type="MD&A",
            source_text="Current text."
        ),
        ManagementTone(
            id=uuid.uuid4(),
            company_id=company_id,
            sentiment=Sentiment.POSITIVE,
            confidence_level=ConfidenceLevel.CONFIDENT,
            hedging_score=0.1,
            positive_score=0.8,
            negative_score=0.1,
            confidence_score=0.9,
            source_type="MD&A",
            source_text="Prior text."
        )
    )
    assert t1.evolution_type == ToneEvolutionType.MORE_NEGATIVE

    # CONFIDENT to CAUTIOUS -> MORE_CAUTIOUS
    t2 = classifier.classify(
        ManagementTone(
            id=uuid.uuid4(),
            company_id=company_id,
            sentiment=Sentiment.NEUTRAL,
            confidence_level=ConfidenceLevel.CAUTIOUS,
            hedging_score=0.5,
            positive_score=0.1,
            negative_score=0.1,
            confidence_score=0.8,
            source_type="MD&A",
            source_text="Current text."
        ),
        ManagementTone(
            id=uuid.uuid4(),
            company_id=company_id,
            sentiment=Sentiment.NEUTRAL,
            confidence_level=ConfidenceLevel.CONFIDENT,
            hedging_score=0.1,
            positive_score=0.1,
            negative_score=0.1,
            confidence_score=0.9,
            source_type="MD&A",
            source_text="Prior text."
        )
    )
    assert t2.evolution_type == ToneEvolutionType.MORE_CAUTIOUS


@pytest.mark.unit
def test_tone_analysis_gold_dataset_loads() -> None:
    gold = load_analysis_gold()
    assert len(gold) == 3
    assert all(ex.expected for ex in gold)


@pytest.mark.unit
def test_tone_analysis_evaluator() -> None:
    report = ToneAnalysisEvaluator().evaluate(load_analysis_gold())
    assert report.sentiment_accuracy == 1.0
    assert report.confidence_level_accuracy == 1.0
    assert report.hedging_error_rate == 0.0


@pytest.mark.unit
def test_tone_evolution_gold_dataset_loads() -> None:
    gold = load_evolution_gold()
    assert len(gold) == 2
    assert all(ex.expected for ex in gold)


@pytest.mark.unit
def test_tone_evolution_evaluator() -> None:
    report = ToneEvolutionEvaluator().evaluate(load_evolution_gold())
    assert report.accuracy == 1.0
    assert report.precision == 1.0
    assert report.recall == 1.0
