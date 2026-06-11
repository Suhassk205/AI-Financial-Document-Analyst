"""Unit tests for Phase 5 Tone Evaluation Modules (Analysis and Evolution)."""

from __future__ import annotations

import uuid
import pytest

from app.tone.analysis.evaluation import (
    GoldExample,
    ToneAnalysisEvaluator,
    load_gold_dataset as load_analysis_gold_dataset
)
from app.tone.evolution.evaluation import (
    GoldEvolutionExample,
    MockManagementTone,
    ToneEvolutionEvaluator,
    load_gold_dataset as load_evolution_gold_dataset
)


def test_load_analysis_gold_dataset() -> None:
    # Ensure loading gold dataset succeeds and contains valid examples
    examples = load_analysis_gold_dataset()
    assert len(examples) >= 1
    assert isinstance(examples[0], GoldExample)
    assert examples[0].text is not None
    assert "sentiment" in examples[0].expected


def test_load_evolution_gold_dataset() -> None:
    # Ensure loading evolution gold dataset succeeds and contains valid examples
    examples = load_evolution_gold_dataset()
    assert len(examples) >= 1
    assert isinstance(examples[0], GoldEvolutionExample)
    assert len(examples[0].prior) >= 1
    assert len(examples[0].current) >= 1
    assert "evolution_type" in examples[0].expected[0]


def test_tone_analysis_evaluator_metrics() -> None:
    # Test evaluation metrics calculation with mock examples
    chunk_1_id = str(uuid.uuid4())
    chunk_2_id = str(uuid.uuid4())
    examples = [
        GoldExample(
            id=chunk_1_id,
            text="The company experienced substantial profit growth.",
            section="Management Commentary",
            fiscal_year=2026,
            expected={
                "sentiment": "POSITIVE",
                "confidence_level": "VERY_CONFIDENT",
                "min_hedging_score": 0.0,
                "max_hedging_score": 0.2
            }
        ),
        GoldExample(
            id=chunk_2_id,
            text="There is uncertainty regarding the future regulatory approval.",
            section="Outlook",
            fiscal_year=2026,
            expected={
                "sentiment": "NEUTRAL",
                "confidence_level": "CAUTIOUS",
                "min_hedging_score": 0.2,
                "max_hedging_score": 0.8
            }
        )
    ]

    evaluator = ToneAnalysisEvaluator()
    report = evaluator.evaluate(examples)

    assert report.num_examples == 2
    assert 0.0 <= report.sentiment_accuracy <= 1.0
    assert 0.0 <= report.confidence_level_accuracy <= 1.0
    assert 0.0 <= report.hedging_error_rate <= 1.0
    assert report.average_confidence >= 0.0
    assert "POSITIVE" in report.per_sentiment or "NEUTRAL" in report.per_sentiment


def test_tone_evolution_evaluator_metrics() -> None:
    # Test evolution evaluation metrics calculation with mock examples
    prior_tones = [
        MockManagementTone(
            id="tone-2023-1",
            source_type="Management Commentary",
            sentiment="NEGATIVE",
            confidence_level="CAUTIOUS",
            hedging_score=0.5,
            positive_score=0.1,
            negative_score=0.6,
            confidence_score=0.4,
            extraction_method="RULE_BASED",
            source_text="We have a lot of problems."
        )
    ]

    current_tones = [
        MockManagementTone(
            id="tone-2024-1",
            source_type="Management Commentary",
            sentiment="POSITIVE",
            confidence_level="VERY_CONFIDENT",
            hedging_score=0.1,
            positive_score=0.8,
            negative_score=0.05,
            confidence_score=0.9,
            extraction_method="RULE_BASED",
            source_text="Everything is amazing now."
        )
    ]

    examples = [
        GoldEvolutionExample(
            id="ev-1",
            company_id="00000000-0000-0000-0000-000000000001",
            prior=prior_tones,
            current=current_tones,
            expected=[
                {
                    "previous_tone_id": "tone-2023-1",
                    "current_tone_id": "tone-2024-1",
                    "evolution_type": "MORE_POSITIVE"
                }
            ]
        )
    ]

    evaluator = ToneEvolutionEvaluator()
    report = evaluator.evaluate(examples)

    assert report.num_examples == 1
    assert report.total_expected == 1
    assert report.total_generated == 1
    assert report.correct == 1
    assert report.accuracy == 1.0
    assert report.precision == 1.0
    assert report.recall == 1.0
    assert "MORE_POSITIVE" in report.per_evolution_type
