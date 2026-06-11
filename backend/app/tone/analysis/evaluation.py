"""Management tone analysis offline evaluation (Phase 5)."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.tone.analysis.models import ToneChunkInput
from app.tone.analysis.hybrid_analyzer import HybridToneAnalyzer

_DEFAULT_PATH = Path(__file__).with_name("gold_dataset.json")


@dataclass
class GoldExample:
    id: str
    text: str
    section: str | None
    fiscal_year: int | None
    expected: dict


@dataclass
class ToneAnalysisEvaluationReport:
    num_examples: int
    sentiment_accuracy: float
    confidence_level_accuracy: float
    hedging_error_rate: float  # Fraction of examples where hedging score falls outside expected bounds
    average_confidence: float
    per_sentiment: dict[str, dict] = field(default_factory=dict)

    def as_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


def load_gold_dataset(path: str | Path | None = None) -> list[GoldExample]:
    p = Path(path) if path else _DEFAULT_PATH
    raw = json.loads(p.read_text(encoding="utf-8"))
    return [
        GoldExample(
            id=e["id"],
            text=e["text"],
            section=e.get("section"),
            fiscal_year=e.get("fiscal_year"),
            expected=e["expected"],
        )
        for e in raw.get("examples", [])
    ]


class ToneAnalysisEvaluator:
    def __init__(self, analyzer: HybridToneAnalyzer | None = None) -> None:
        self.analyzer = analyzer or HybridToneAnalyzer()

    def evaluate(self, examples: list[GoldExample]) -> ToneAnalysisEvaluationReport:
        if not examples:
            return ToneAnalysisEvaluationReport(0, 0.0, 0.0, 0.0, 0.0)

        sentiment_correct = 0
        conf_level_correct = 0
        hedging_out_of_bounds = 0
        total_confidence = 0.0

        per_sentiment = {}

        # Run analysis on all examples
        company_id = uuid.uuid4()
        inputs = [
            ToneChunkInput(
                chunk_id=ex.id,
                text=ex.text,
                normalized_section_name=ex.section,
                fiscal_year=ex.fiscal_year or 2026,
                fiscal_quarter=1,
            )
            for ex in examples
        ]

        result = self.analyzer.analyze(company_id, inputs)
        records_map = {str(r.source_chunk_id) if r.source_chunk_id else "": r for r in result.tone_records}

        for ex in examples:
            rec = records_map.get(str(ex.id))
            if not rec:
                continue

            exp = ex.expected
            sentiment_match = (rec.sentiment.value == exp["sentiment"])
            conf_level_match = (rec.confidence_level.value == exp["confidence_level"])

            if sentiment_match:
                sentiment_correct += 1
            if conf_level_match:
                conf_level_correct += 1

            min_hedge = exp.get("min_hedging_score", 0.0)
            max_hedge = exp.get("max_hedging_score", 1.0)
            if not (min_hedge <= rec.hedging_score <= max_hedge):
                hedging_out_of_bounds += 1

            total_confidence += rec.confidence_score

            sent_stats = per_sentiment.setdefault(exp["sentiment"], {"total": 0, "correct": 0})
            sent_stats["total"] += 1
            if sentiment_match:
                sent_stats["correct"] += 1

        n = len(examples)
        return ToneAnalysisEvaluationReport(
            num_examples=n,
            sentiment_accuracy=round(sentiment_correct / n, 4),
            confidence_level_accuracy=round(conf_level_correct / n, 4),
            hedging_error_rate=round(hedging_out_of_bounds / n, 4),
            average_confidence=round(total_confidence / n, 4),
            per_sentiment=per_sentiment,
        )
