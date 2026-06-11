"""Search endpoints (Phase 2B vector + Phase 2C hybrid). Mounted at /api/v1/search.

Retrieval only: returns semantically relevant chunks + scores, optionally scoped
by structured metadata filters. No answers, no generation, no query rewriting,
no re-ranking.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.retrieval.hybrid import (
    HybridRetrievalService,
    RetrievalContext,
    list_profiles,
)
from app.retrieval.hybrid.hybrid_retriever import HybridOutcome
from app.retrieval.search import VectorSearchService
from app.retrieval.search.retrieval_models import SearchOutcome, SearchResult
from app.schemas.search import (
    HybridDebugResponse,
    HybridSearchRequest,
    HybridSearchResponse,
    HybridTimingsOut,
    QueryEmbeddingStatsOut,
    RetrievalProfileOut,
    RetrievalProfilesResponse,
    SearchDebugResponse,
    SearchRequest,
    SearchResponse,
    SearchResultOut,
    SearchTimingsOut,
)

router = APIRouter()


def get_search_service(db: AsyncSession = Depends(get_db)) -> VectorSearchService:
    """Provide a vector search service (default: real Gemini query embedder).

    Injectable so tests can supply a deterministic embedder without a live API.
    """
    return VectorSearchService(db)


def get_hybrid_service(db: AsyncSession = Depends(get_db)) -> HybridRetrievalService:
    """Provide a hybrid retrieval service (injectable for tests)."""
    return HybridRetrievalService(db)


def _result_out(r: SearchResult) -> SearchResultOut:
    return SearchResultOut(
        chunk_id=r.chunk_id,
        report_id=r.report_id,
        section_id=r.section_id,
        score=r.score,
        chunk_text=r.chunk_text,
        metadata=r.metadata,
    )


def _timings_out(outcome: SearchOutcome) -> SearchTimingsOut:
    return SearchTimingsOut(**outcome.timings.as_dict())


@router.post(
    "/vector",
    response_model=SearchResponse,
    summary="Vector similarity search (top-K semantically relevant chunks)",
)
async def vector_search(
    payload: SearchRequest,
    service: VectorSearchService = Depends(get_search_service),
) -> SearchResponse:
    outcome = await service.search(payload.query, top_k=payload.top_k)
    return SearchResponse(
        query=payload.query,
        top_k=outcome.requested_top_k,
        count=outcome.returned,
        timings=_timings_out(outcome),
        results=[_result_out(r) for r in outcome.results],
    )


@router.post(
    "/debug",
    response_model=SearchDebugResponse,
    summary="Vector search diagnostics (query embedding stats + scores + timings)",
)
async def debug_search(
    payload: SearchRequest,
    service: VectorSearchService = Depends(get_search_service),
) -> SearchDebugResponse:
    outcome, stats = await service.run(payload.query, top_k=payload.top_k)
    return SearchDebugResponse(
        query=payload.query,
        top_k=outcome.requested_top_k,
        count=outcome.returned,
        query_embedding=QueryEmbeddingStatsOut(**asdict(stats)),
        timings=_timings_out(outcome),
        results=[_result_out(r) for r in outcome.results],
    )


# ---- Phase 2C: hybrid retrieval ----------------------------------------------


def _context(payload: HybridSearchRequest) -> RetrievalContext:
    f = payload.filters
    return RetrievalContext(
        company_id=f.company_id,
        report_id=f.report_id,
        year=f.year,
        quarter=f.quarter,
        report_type=f.report_type,
        section_name=f.section_name,
        normalized_section_name=f.normalized_section_name,
    )


def _hybrid_timings(outcome: HybridOutcome) -> HybridTimingsOut:
    return HybridTimingsOut(**outcome.timings.as_dict())


@router.post(
    "/hybrid",
    response_model=HybridSearchResponse,
    summary="Hybrid retrieval: metadata filters + vector search",
)
async def hybrid_search(
    payload: HybridSearchRequest,
    service: HybridRetrievalService = Depends(get_hybrid_service),
) -> HybridSearchResponse:
    outcome = await service.run(
        payload.query, _context(payload), top_k=payload.top_k, profile=payload.profile
    )
    return HybridSearchResponse(
        query=payload.query,
        profile=outcome.profile.name,
        top_k=outcome.top_k,
        count=len(outcome.results),
        candidate_count=outcome.candidate_count,
        applied_filters=outcome.applied_filters,
        timings=_hybrid_timings(outcome),
        results=[_result_out(r) for r in outcome.results],
    )


@router.post(
    "/hybrid/debug",
    response_model=HybridDebugResponse,
    summary="Hybrid retrieval diagnostics (filters + candidate count + params + scores)",
)
async def hybrid_debug(
    payload: HybridSearchRequest,
    service: HybridRetrievalService = Depends(get_hybrid_service),
) -> HybridDebugResponse:
    outcome = await service.run(
        payload.query, _context(payload), top_k=payload.top_k, profile=payload.profile
    )
    return HybridDebugResponse(
        query=payload.query,
        profile=outcome.profile.name,
        top_k=outcome.top_k,
        count=len(outcome.results),
        candidate_count=outcome.candidate_count,
        applied_filters=outcome.applied_filters,
        search_parameters={
            "distance_metric": settings.search_distance_metric,
            "hnsw_ef_search": settings.hnsw_ef_search,
            "preferred_sections": list(outcome.profile.preferred_sections),
            "max_candidates": outcome.profile.max_candidates,
        },
        query_embedding=QueryEmbeddingStatsOut(**asdict(outcome.query_embedding)),
        timings=_hybrid_timings(outcome),
        results=[_result_out(r) for r in outcome.results],
    )


@router.get(
    "/profiles",
    response_model=RetrievalProfilesResponse,
    summary="List available retrieval profiles",
)
async def get_profiles() -> RetrievalProfilesResponse:
    return RetrievalProfilesResponse(
        profiles=[RetrievalProfileOut(**p.as_dict()) for p in list_profiles()]
    )
