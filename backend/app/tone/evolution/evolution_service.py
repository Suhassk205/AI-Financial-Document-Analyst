"""Service orchestrating tone evolution generation across periods (Phase 5)."""

from __future__ import annotations

import uuid

from app.core.logging import get_logger
from app.models.management_tone import ManagementTone
from app.tone.evolution.models import ExtractedToneEvolution, ToneEvolutionCandidate
from app.tone.evolution.tone_matcher import ToneMatcher
from app.tone.evolution.evolution_classifier import ToneEvolutionClassifier
from app.tone.evolution.validators import ToneEvolutionValidator

log = get_logger(__name__)


class ToneEvolutionService:
    """Orchestrates matching current and prior period tone records, and classifying evolution."""

    def __init__(
        self,
        *,
        matcher: ToneMatcher | None = None,
        classifier: ToneEvolutionClassifier | None = None,
        validator: ToneEvolutionValidator | None = None,
    ) -> None:
        self.matcher = matcher or ToneMatcher()
        self.classifier = classifier or ToneEvolutionClassifier()
        self.validator = validator or ToneEvolutionValidator()

    def generate_evolution(
        self,
        company_id: uuid.UUID,
        current_records: list[ManagementTone],
        previous_records: list[ManagementTone],
    ) -> list[ExtractedToneEvolution]:
        """Match and classify tone evolution.

        Only produces evolution records for successfully matched current/previous pairs.
        """
        matches = self.matcher.match(current_records, previous_records)
        evolutions: list[ExtractedToneEvolution] = []

        for curr, prev in matches:
            if curr is None or prev is None:
                # Skip unmatched new/removed tone areas since PoP requires both periods
                continue

            try:
                candidate = self.classifier.classify(curr, prev)
                vr = self.validator.validate(candidate)
                if not vr.is_valid:
                    log.warning(
                        "tone_evolution.validation_failed",
                        current_id=curr.id,
                        previous_id=prev.id,
                        errors=vr.errors,
                    )
                    continue

                evolutions.append(
                    ExtractedToneEvolution(
                        company_id=company_id,
                        current_tone_id=candidate.current_tone_id,
                        previous_tone_id=candidate.previous_tone_id,
                        evolution_type=candidate.evolution_type,
                        confidence_score=candidate.confidence_score,
                        explanation=candidate.explanation,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                log.error(
                    "tone_evolution.classification_failed",
                    current_id=curr.id,
                    previous_id=prev.id,
                    error=str(exc),
                )

        log.info(
            "tone_evolution.run_complete",
            company_id=company_id,
            total_matches=len(matches),
            evolutions=len(evolutions),
        )
        return evolutions
