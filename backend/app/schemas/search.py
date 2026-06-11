"""Pydantic schemas for the vector-search API (Phase 2B).

Retrieval only — these carry chunks + similarity scores, never answers.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(..., description="Natural-language search query", min_length=1)
    top_k: int = Field(
        10, ge=5, le=50, description="Number of results to return (5–50, default 10)"
    )


class SearchResultOut(BaseModel):
    chunk_id: uuid.UUID
    report_id: uuid.UUID
    section_id: uuid.UUID | None
    score: float
    chunk_text: str
    metadata: dict


class SearchTimingsOut(BaseModel):
    embedding_ms: float
    vector_search_ms: float
    total_ms: float


class SearchResponse(BaseModel):
    query: str
    top_k: int
    count: int
    timings: SearchTimingsOut
    results: list[SearchResultOut]


class QueryEmbeddingStatsOut(BaseModel):
    dimension: int
    norm: float
    preview: list[float]
    model: str
    task_type: str


class SearchDebugResponse(BaseModel):
    """Retrieval diagnostics: query → embedding stats → chunks → scores → timings."""

    query: str
    top_k: int
    count: int
    query_embedding: QueryEmbeddingStatsOut
    timings: SearchTimingsOut
    results: list[SearchResultOut]


# ---- Phase 2C: hybrid retrieval ----------------------------------------------


class HybridFilters(BaseModel):
    """All-optional structured constraints. Invalid UUIDs are rejected by Pydantic."""

    company_id: uuid.UUID | None = None
    report_id: uuid.UUID | None = None
    year: int | None = None
    quarter: int | None = None
    report_type: str | None = None
    section_name: str | None = None
    normalized_section_name: str | None = None


class HybridSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural-language search query")
    top_k: int | None = Field(
        None, ge=5, le=50, description="Results to return (5–50; default from profile)"
    )
    profile: str | None = Field(None, description="Retrieval profile (default GENERAL)")
    filters: HybridFilters = Field(default_factory=HybridFilters)


class HybridTimingsOut(BaseModel):
    embedding_ms: float
    filter_ms: float
    vector_search_ms: float
    total_ms: float


class HybridSearchResponse(BaseModel):
    query: str
    profile: str
    top_k: int
    count: int
    candidate_count: int
    applied_filters: dict
    timings: HybridTimingsOut
    results: list[SearchResultOut]


class HybridDebugResponse(BaseModel):
    """Hybrid diagnostics: applied filters → candidate count → params → chunks → scores."""

    query: str
    profile: str
    top_k: int
    count: int
    candidate_count: int
    applied_filters: dict
    search_parameters: dict
    query_embedding: QueryEmbeddingStatsOut
    timings: HybridTimingsOut
    results: list[SearchResultOut]


class RetrievalProfileOut(BaseModel):
    name: str
    description: str
    preferred_sections: list[str]
    default_top_k: int
    max_candidates: int


class RetrievalProfilesResponse(BaseModel):
    profiles: list[RetrievalProfileOut]
