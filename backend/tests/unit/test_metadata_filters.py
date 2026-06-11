"""Unit tests for the metadata filter builder (Phase 2C)."""

from __future__ import annotations

import uuid

import pytest
from app.retrieval.hybrid.metadata_filters import build_filter_plan
from app.retrieval.hybrid.query_context import RetrievalContext


@pytest.mark.unit
def test_empty_context_yields_no_conditions() -> None:
    plan = build_filter_plan(RetrievalContext())
    assert plan.conditions == []
    assert plan.needs_report_join is False
    assert plan.applied == {}


@pytest.mark.unit
def test_report_id_only_needs_no_join() -> None:
    rid = uuid.uuid4()
    plan = build_filter_plan(RetrievalContext(report_id=rid))
    assert len(plan.conditions) == 1
    assert plan.needs_report_join is False
    assert plan.applied["report_id"] == str(rid)


@pytest.mark.unit
@pytest.mark.parametrize(
    "ctx_kwargs,key",
    [
        ({"company_id": uuid.uuid4()}, "company_id"),
        ({"year": 2024}, "year"),
        ({"quarter": 2}, "quarter"),
        ({"report_type": "10-Q"}, "report_type"),
    ],
)
def test_report_level_filters_need_join(ctx_kwargs, key) -> None:
    plan = build_filter_plan(RetrievalContext(**ctx_kwargs))
    assert plan.needs_report_join is True
    assert key in plan.applied


@pytest.mark.unit
def test_section_filters_use_metadata_no_join() -> None:
    plan = build_filter_plan(RetrievalContext(normalized_section_name="Risk Factors"))
    assert plan.needs_report_join is False
    assert len(plan.conditions) == 1
    assert plan.applied["normalized_section_name"] == "Risk Factors"


@pytest.mark.unit
def test_preferred_sections_applied_when_no_explicit_section() -> None:
    plan = build_filter_plan(
        RetrievalContext(), preferred_sections=("Risk Factors", "Legal Proceedings")
    )
    assert len(plan.conditions) == 1                       # an OR over preferred sections
    assert plan.applied["preferred_sections"] == ["Risk Factors", "Legal Proceedings"]


@pytest.mark.unit
def test_explicit_section_overrides_preferred() -> None:
    plan = build_filter_plan(
        RetrievalContext(normalized_section_name="MD&A"),
        preferred_sections=("Risk Factors",),
    )
    assert "preferred_sections" not in plan.applied
    assert plan.applied["normalized_section_name"] == "MD&A"


@pytest.mark.unit
def test_multiple_filters_combine() -> None:
    plan = build_filter_plan(
        RetrievalContext(company_id=uuid.uuid4(), year=2024, normalized_section_name="Risk Factors")
    )
    assert len(plan.conditions) == 3
    assert plan.needs_report_join is True
    assert set(plan.applied) == {"company_id", "year", "normalized_section_name"}
