"""Retrieval context (Phase 2C).

`RetrievalContext` encapsulates the (all-optional) structured constraints applied
to a search. It is the object future phases (re-ranking, RAG, agents) will pass
around to scope retrieval. This module owns the *pure* validation (ranges, enum,
taxonomy, self-conflicts) — DB-backed checks (existence, cross-row consistency)
live in the service.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.ingestion.section_detection.taxonomy import get_taxonomy
from app.models.enums import ReportType
from app.retrieval.hybrid.retrieval_exceptions import (
    ConflictingFiltersError,
    InvalidFilterError,
    UnknownSectionError,
)

_MIN_YEAR, _MAX_YEAR = 1900, 2200


@dataclass
class RetrievalContext:
    """Optional structured constraints for a retrieval. Nothing is mandatory."""

    company_id: uuid.UUID | None = None
    report_id: uuid.UUID | None = None
    year: int | None = None
    quarter: int | None = None
    report_type: str | None = None
    section_name: str | None = None
    normalized_section_name: str | None = None

    def has_filters(self) -> bool:
        return any(
            v is not None
            for v in (
                self.company_id,
                self.report_id,
                self.year,
                self.quarter,
                self.report_type,
                self.section_name,
                self.normalized_section_name,
            )
        )

    def applied(self) -> dict:
        """Non-null filters as a JSON-friendly dict (debug/observability)."""
        out: dict = {}
        for key in (
            "company_id", "report_id", "year", "quarter",
            "report_type", "section_name", "normalized_section_name",
        ):
            value = getattr(self, key)
            if value is not None:
                out[key] = str(value) if isinstance(value, uuid.UUID) else value
        return out

    def validate(self) -> None:
        """Pure validation (no DB). Raises a 422-mapped error on bad input."""
        if self.year is not None and not (_MIN_YEAR <= self.year <= _MAX_YEAR):
            raise InvalidFilterError(
                f"year must be between {_MIN_YEAR} and {_MAX_YEAR}",
                details={"year": self.year},
            )
        if self.quarter is not None and not (1 <= self.quarter <= 4):
            raise InvalidFilterError(
                "quarter must be between 1 and 4", details={"quarter": self.quarter}
            )
        if self.report_type is not None and self.report_type not in {t.value for t in ReportType}:
            raise InvalidFilterError(
                "unknown report_type",
                details={"report_type": self.report_type,
                         "allowed": [t.value for t in ReportType]},
            )
        if self.normalized_section_name is not None and not get_taxonomy().is_canonical(
            self.normalized_section_name
        ):
            raise UnknownSectionError(
                "unknown normalized_section_name (not in taxonomy)",
                details={"normalized_section_name": self.normalized_section_name},
            )
        # Self-conflict: a 10-K is an annual filing — it has no quarter.
        if self.quarter is not None and self.report_type == ReportType.TEN_K.value:
            raise ConflictingFiltersError(
                "quarter is not valid for a 10-K (annual report)",
                details={"report_type": self.report_type, "quarter": self.quarter},
            )
