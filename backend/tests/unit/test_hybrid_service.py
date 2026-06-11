"""Unit tests for HybridRetrievalService orchestration (Phase 2C).

The three DB-touching methods are stubbed so orchestration (validation order,
profile/top_k resolution, filter-plan assembly, outcome) is tested with no DB.
"""

from __future__ import annotations

import uuid

import pytest
from app.retrieval.hybrid.hybrid_retriever import HybridRetrievalService
from app.retrieval.hybrid.query_context import RetrievalContext
from app.retrieval.hybrid.retrieval_exceptions import (
    UnknownProfileError,
    UnknownSectionError,
)
from app.retrieval.search.retrieval_models import QueryEmbeddingStats, SearchResult
from app.retrieval.search.search_exceptions import InvalidTopKError

DIM = 4


class FakeEmbedder:
    def embed(self, query):
        stats = QueryEmbeddingStats(
            dimension=DIM, norm=1.0, preview=[0.1], model="m", task_type="RETRIEVAL_QUERY"
        )
        return [0.1] * DIM, stats


def _results(n):
    return [
        SearchResult(
            chunk_id=uuid.uuid4(), report_id=uuid.uuid4(), section_id=None,
            score=round(1.0 - i * 0.1, 4), chunk_text=f"c{i}", metadata={},
        )
        for i in range(n)
    ]


def _service(*, candidate_count=5, results=None):
    svc = HybridRetrievalService(None, query_embedder=FakeEmbedder())

    async def _noop_validate(ctx):
        return None

    async def _count(plan):
        return candidate_count

    async def _search(vec, plan, k):
        return (results if results is not None else _results(k))[:k]

    svc._validate_db = _noop_validate
    svc._candidate_count = _count
    svc._filtered_search = _search
    return svc


@pytest.mark.unit
async def test_general_profile_default_top_k_and_outcome() -> None:
    svc = _service(candidate_count=7)
    outcome = await svc.run("supply chain risk", RetrievalContext())
    assert outcome.profile.name == "GENERAL"
    assert outcome.top_k == 10                      # GENERAL default
    assert outcome.candidate_count == 7
    assert outcome.timings.total_ms >= 0.0
    assert outcome.query_embedding.dimension == DIM


@pytest.mark.unit
async def test_profile_resolution_and_preferred_sections_in_plan() -> None:
    svc = _service()
    outcome = await svc.run("risk", RetrievalContext(), profile="RISK_ANALYSIS")
    assert outcome.profile.name == "RISK_ANALYSIS"
    assert outcome.applied_filters.get("preferred_sections")  # profile injected a section filter


@pytest.mark.unit
async def test_explicit_top_k_overrides_profile_default() -> None:
    svc = _service()
    outcome = await svc.run("q", RetrievalContext(), top_k=5)
    assert outcome.top_k == 5


@pytest.mark.unit
async def test_out_of_range_top_k_raises() -> None:
    svc = _service()
    with pytest.raises(InvalidTopKError):
        await svc.run("q", RetrievalContext(), top_k=100)


@pytest.mark.unit
async def test_pure_validation_runs_before_db() -> None:
    svc = _service()
    with pytest.raises(UnknownSectionError):
        await svc.run("q", RetrievalContext(normalized_section_name="Nope"))


@pytest.mark.unit
async def test_unknown_profile_raises() -> None:
    svc = _service()
    with pytest.raises(UnknownProfileError):
        await svc.run("q", RetrievalContext(), profile="BOGUS")


@pytest.mark.unit
async def test_applied_filters_reflect_context() -> None:
    svc = _service()
    cid = uuid.uuid4()
    outcome = await svc.run("q", RetrievalContext(company_id=cid, year=2024))
    assert outcome.applied_filters["company_id"] == str(cid)
    assert outcome.applied_filters["year"] == 2024
