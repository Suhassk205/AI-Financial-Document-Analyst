"""Tone evolution offline evaluation (Phase 5)."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.models.management_tone import ManagementTone
from app.tone.evolution.evolution_service import ToneEvolutionService

_DEFAULT_PATH = Path(__file__).with_name("gold_dataset.json")


@dataclass
class MockManagementTone:
    id: Any
    source_type: str
    sentiment: str
    confidence_level: str
    hedging_score: float
    positive_score: float
    negative_score: float
    confidence_score: float
    extraction_method: str
    source_text: str


@dataclass
class GoldEvolutionExample:
    id: str
    company_id: str
    prior: list[MockManagementTone]
    current: list[MockManagementTone]
    expected: list[dict]


@dataclass
class ToneEvolutionEvaluationReport:
    num_examples: int
    total_expected: int
    total_generated: int
    correct: int
    accuracy: float
    precision: float
    recall: float
    per_evolution_type: dict[str, dict] = field(default_factory=dict)

    def as_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


def load_gold_dataset(path: str | Path | None = None) -> list[GoldEvolutionExample]:
    p = Path(path) if path else _DEFAULT_PATH
    raw = json.loads(p.read_text(encoding="utf-8"))

    examples = []
    for e in raw.get("examples", []):
        prior_list = [
            MockManagementTone(
                id=uuid.UUID(r["id"]) if isinstance(r["id"], str) and len(r["id"]) == 36 else r["id"],
                source_type=r["source_type"],
                sentiment=r["sentiment"],
                confidence_level=r["confidence_level"],
                hedging_score=r["hedging_score"],
                positive_score=r["positive_score"],
                negative_score=r["negative_score"],
                confidence_score=r["confidence_score"],
                extraction_method=r["extraction_method"],
                source_text=r["source_text"],
            )
            for r in e.get("prior", [])
        ]
        curr_list = [
            MockManagementTone(
                id=uuid.UUID(r["id"]) if isinstance(r["id"], str) and len(r["id"]) == 36 else r["id"],
                source_type=r["source_type"],
                sentiment=r["sentiment"],
                confidence_level=r["confidence_level"],
                hedging_score=r["hedging_score"],
                positive_score=r["positive_score"],
                negative_score=r["negative_score"],
                confidence_score=r["confidence_score"],
                extraction_method=r["extraction_method"],
                source_text=r["source_text"],
            )
            for r in e.get("current", [])
        ]
        examples.append(
            GoldEvolutionExample(
                id=e["id"],
                company_id=e["company_id"],
                prior=prior_list,
                current=curr_list,
                expected=e.get("expected", []),
            )
        )
    return examples


class ToneEvolutionEvaluator:
    def __init__(self, service: ToneEvolutionService | None = None) -> None:
        self.service = service or ToneEvolutionService()

    def evaluate(self, examples: list[GoldEvolutionExample]) -> ToneEvolutionEvaluationReport:
        total_expected = 0
        total_generated = 0
        correct = 0
        per_evolution_type = {}

        for ex in examples:
            company_id = uuid.UUID(ex.company_id)

            # We need to map MockManagementTone to actual ManagementTone model instances for the service
            # since the service expects SQLAlchemy model instances.
            current_models = []
            for m in ex.current:
                db_model = ManagementTone(
                    id=m.id if isinstance(m.id, uuid.UUID) else uuid.uuid4(),
                    company_id=company_id,
                    source_type=m.source_type,
                    sentiment=m.sentiment,
                    confidence_level=m.confidence_level,
                    hedging_score=m.hedging_score,
                    positive_score=m.positive_score,
                    negative_score=m.negative_score,
                    confidence_score=m.confidence_score,
                    extraction_method=m.extraction_method,
                    source_text=m.source_text,
                )
                current_models.append(db_model)

            prior_models = []
            for m in ex.prior:
                db_model = ManagementTone(
                    id=m.id if isinstance(m.id, uuid.UUID) else uuid.uuid4(),
                    company_id=company_id,
                    source_type=m.source_type,
                    sentiment=m.sentiment,
                    confidence_level=m.confidence_level,
                    hedging_score=m.hedging_score,
                    positive_score=m.positive_score,
                    negative_score=m.negative_score,
                    confidence_score=m.confidence_score,
                    extraction_method=m.extraction_method,
                    source_text=m.source_text,
                )
                prior_models.append(db_model)

            # Map the mock IDs to database model IDs
            current_id_map = {ex.current[i].id: current_models[i].id for i in range(len(ex.current))}
            prior_id_map = {ex.prior[i].id: prior_models[i].id for i in range(len(ex.prior))}

            generated = self.service.generate_evolution(
                company_id,
                current_models,
                prior_models,
            )

            total_generated += len(generated)

            generated_map = {}
            for r in generated:
                prev_id = r.previous_tone_id
                curr_id = r.current_tone_id
                generated_map[(prev_id, curr_id)] = r.evolution_type.value

            for exp in ex.expected:
                total_expected += 1
                etype = exp["evolution_type"]
                stats = per_evolution_type.setdefault(etype, {"expected": 0, "correct": 0})
                stats["expected"] += 1

                exp_prev = prior_id_map.get(exp["previous_tone_id"])
                exp_curr = current_id_map.get(exp["current_tone_id"])

                got_type = generated_map.get((exp_prev, exp_curr))
                if got_type == etype:
                    correct += 1
                    stats["correct"] += 1

        return ToneEvolutionEvaluationReport(
            num_examples=len(examples),
            total_expected=total_expected,
            total_generated=total_generated,
            correct=correct,
            accuracy=round(correct / total_expected, 4) if total_expected else 0.0,
            precision=round(correct / total_generated, 4) if total_generated else 0.0,
            recall=round(correct / total_expected, 4) if total_expected else 0.0,
            per_evolution_type=per_evolution_type,
        )
