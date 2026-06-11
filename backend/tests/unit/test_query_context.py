"""Unit tests for RetrievalContext validation (Phase 2C)."""

from __future__ import annotations

import uuid

import pytest
from app.retrieval.hybrid.query_context import RetrievalContext
from app.retrieval.hybrid.retrieval_exceptions import (
    ConflictingFiltersError,
    InvalidFilterError,
    UnknownSectionError,
)


@pytest.mark.unit
def test_empty_context_has_no_filters() -> None:
    ctx = RetrievalContext()
    assert ctx.has_filters() is False
    assert ctx.applied() == {}
    ctx.validate()  # no error


@pytest.mark.unit
def test_applied_lists_only_set_filters() -> None:
    cid = uuid.uuid4()
    ctx = RetrievalContext(company_id=cid, year=2024, normalized_section_name="Risk Factors")
    applied = ctx.applied()
    assert applied == {
        "company_id": str(cid),
        "year": 2024,
        "normalized_section_name": "Risk Factors",
    }
    assert ctx.has_filters() is True


@pytest.mark.unit
def test_valid_context_passes() -> None:
    RetrievalContext(
        year=2024, quarter=3, report_type="10-Q", normalized_section_name="MD&A"
    ).validate()


@pytest.mark.unit
@pytest.mark.parametrize("year", [1800, 2300])
def test_bad_year_raises(year: int) -> None:
    with pytest.raises(InvalidFilterError):
        RetrievalContext(year=year).validate()


@pytest.mark.unit
@pytest.mark.parametrize("quarter", [0, 5])
def test_bad_quarter_raises(quarter: int) -> None:
    with pytest.raises(InvalidFilterError):
        RetrievalContext(quarter=quarter).validate()


@pytest.mark.unit
def test_unknown_report_type_raises() -> None:
    with pytest.raises(InvalidFilterError):
        RetrievalContext(report_type="10-Z").validate()


@pytest.mark.unit
def test_unknown_section_raises() -> None:
    with pytest.raises(UnknownSectionError):
        RetrievalContext(normalized_section_name="Made Up Section").validate()


@pytest.mark.unit
def test_quarter_on_10k_is_conflict() -> None:
    with pytest.raises(ConflictingFiltersError):
        RetrievalContext(report_type="10-K", quarter=2).validate()
