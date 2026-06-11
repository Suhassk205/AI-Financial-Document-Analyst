"""Hybrid-retrieval exceptions (Phase 2C).

Subclass the Phase 2B `SearchError` (→ `AppError`) so they map onto the existing
HTTP envelope. Filter problems are user errors (4xx), not server faults.
"""

from __future__ import annotations

from app.retrieval.search.search_exceptions import SearchError


class HybridSearchError(SearchError):
    status_code = 500
    code = "HYBRID_SEARCH_ERROR"


class InvalidFilterError(SearchError):
    """A filter value is out of range / not a recognised value."""

    status_code = 422
    code = "INVALID_FILTER"


class UnknownSectionError(SearchError):
    """A `normalized_section_name` filter is not in the canonical taxonomy."""

    status_code = 422
    code = "UNKNOWN_SECTION"


class ConflictingFiltersError(SearchError):
    """Filters contradict each other (e.g. quarter on a 10-K, or report_id vs company_id)."""

    status_code = 422
    code = "CONFLICTING_FILTERS"


class UnknownProfileError(SearchError):
    status_code = 422
    code = "UNKNOWN_PROFILE"


class FilterTargetNotFoundError(SearchError):
    """A referenced company_id / report_id does not exist."""

    status_code = 404
    code = "FILTER_TARGET_NOT_FOUND"
