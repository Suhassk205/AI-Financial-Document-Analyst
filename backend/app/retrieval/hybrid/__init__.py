"""Hybrid retrieval foundation (Phase 2C).

Metadata filtering + semantic vector search: filter the candidate set FIRST, then
rank within it by cosine similarity. Output is the Phase 2B `SearchResult`
contract, scoped by structured constraints — NO query rewriting, HyDE, re-ranking,
LLM reasoning, or generation.

Public surface:

    from app.retrieval.hybrid import (
        HybridRetrievalService,
        RetrievalContext,
        RetrievalProfile,
        get_profile,
        list_profiles,
    )
"""

from app.retrieval.hybrid.hybrid_retriever import (
    HybridOutcome,
    HybridRetrievalService,
    HybridTimings,
)
from app.retrieval.hybrid.metadata_filters import FilterPlan, build_filter_plan
from app.retrieval.hybrid.query_context import RetrievalContext
from app.retrieval.hybrid.retrieval_exceptions import (
    ConflictingFiltersError,
    FilterTargetNotFoundError,
    HybridSearchError,
    InvalidFilterError,
    UnknownProfileError,
    UnknownSectionError,
)
from app.retrieval.hybrid.retrieval_profiles import (
    PROFILES,
    RetrievalProfile,
    get_profile,
    list_profiles,
)

__all__ = [
    "HybridRetrievalService",
    "HybridOutcome",
    "HybridTimings",
    "RetrievalContext",
    "RetrievalProfile",
    "PROFILES",
    "get_profile",
    "list_profiles",
    "FilterPlan",
    "build_filter_plan",
    "HybridSearchError",
    "InvalidFilterError",
    "UnknownSectionError",
    "ConflictingFiltersError",
    "UnknownProfileError",
    "FilterTargetNotFoundError",
]
