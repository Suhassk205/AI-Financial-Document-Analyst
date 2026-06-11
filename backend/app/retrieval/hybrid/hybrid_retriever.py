"""Hybrid retrieval service (Phase 2C).

Combines structured metadata constraints with semantic vector search, in the
required order:

    query → build query embedding → apply metadata filters → candidate selection
          → vector search (within candidates) → ranked results

Crucially, filtering happens BEFORE similarity ranking: the metadata predicates
are part of the SAME SQL as the cosine `ORDER BY ... LIMIT`, so Postgres
constrains the candidate set first and only ranks within it (for selective
filters it scans the small filtered set exactly — never an ANN scan over the
whole corpus). This is the production-grade "search only relevant content"
pattern; it does NOT vector-search the entire corpus and filter afterwards.

No LLM, no generation, no re-ranking, no post-processing — output is the same
`SearchResult` contract as Phase 2B, scoped by filters.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.company import Company
from app.models.document_chunk import DocumentChunk
from app.models.report import Report
from app.retrieval.embeddings.gemini_provider import GeminiEmbeddingProvider
from app.retrieval.embeddings.provider import EmbeddingProvider
from app.retrieval.hybrid.metadata_filters import FilterPlan, build_filter_plan
from app.retrieval.hybrid.query_context import RetrievalContext
from app.retrieval.hybrid.retrieval_exceptions import (
    ConflictingFiltersError,
    FilterTargetNotFoundError,
)
from app.retrieval.hybrid.retrieval_profiles import RetrievalProfile, get_profile
from app.retrieval.search.query_embedding import QueryEmbedder
from app.retrieval.search.retrieval_models import QueryEmbeddingStats, SearchResult
from app.retrieval.search.search_exceptions import InvalidTopKError

log = get_logger(__name__)


@dataclass
class HybridTimings:
    embedding_ms: float = 0.0
    filter_ms: float = 0.0           # candidate-selection (filtered count) latency
    vector_search_ms: float = 0.0
    total_ms: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {
            "embedding_ms": self.embedding_ms,
            "filter_ms": self.filter_ms,
            "vector_search_ms": self.vector_search_ms,
            "total_ms": self.total_ms,
        }


@dataclass
class HybridOutcome:
    results: list[SearchResult]
    timings: HybridTimings
    candidate_count: int             # filtered chunks considered (pre-ranking)
    applied_filters: dict
    profile: RetrievalProfile
    top_k: int
    query_embedding: QueryEmbeddingStats


class HybridRetrievalService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        provider: EmbeddingProvider | None = None,
        query_embedder: QueryEmbedder | None = None,
    ) -> None:
        self.session = session
        if query_embedder is not None:
            self.query_embedder = query_embedder
        else:
            provider = provider or GeminiEmbeddingProvider.from_settings()
            self.query_embedder = QueryEmbedder(provider)

    def _resolve_top_k(self, top_k: int | None, profile: RetrievalProfile) -> int:
        k = profile.default_top_k if top_k is None else top_k
        if k < settings.search_min_top_k or k > settings.search_max_top_k:
            raise InvalidTopKError(
                f"top_k must be between {settings.search_min_top_k} and "
                f"{settings.search_max_top_k}",
                details={"top_k": k},
            )
        return k

    async def _validate_db(self, ctx: RetrievalContext) -> None:
        """Existence + cross-row consistency checks (DB-backed)."""
        if ctx.report_id is not None:
            report = await self.session.get(Report, ctx.report_id)
            if report is None:
                raise FilterTargetNotFoundError(
                    "report_id not found", details={"report_id": str(ctx.report_id)}
                )
            if ctx.company_id is not None and report.company_id != ctx.company_id:
                raise ConflictingFiltersError("report_id belongs to a different company")
            if ctx.year is not None and report.year != ctx.year:
                raise ConflictingFiltersError("report_id year does not match year filter")
            if ctx.quarter is not None and report.quarter != ctx.quarter:
                raise ConflictingFiltersError("report_id quarter does not match quarter filter")
            if ctx.report_type is not None and report.report_type.value != ctx.report_type:
                raise ConflictingFiltersError(
                    "report_id report_type does not match report_type filter"
                )
        elif ctx.company_id is not None:
            if await self.session.get(Company, ctx.company_id) is None:
                raise FilterTargetNotFoundError(
                    "company_id not found", details={"company_id": str(ctx.company_id)}
                )

    def _base(self, plan: FilterPlan):
        """A select with the embedding-not-null guard, the optional report join,
        and the metadata filters applied."""
        from sqlalchemy.sql import Select

        def apply(stmt: Select) -> Select:
            if plan.needs_report_join:
                stmt = stmt.join(Report, DocumentChunk.report_id == Report.id)
            stmt = stmt.where(DocumentChunk.embedding.is_not(None), *plan.conditions)
            return stmt

        return apply

    async def _candidate_count(self, plan: FilterPlan) -> int:
        apply = self._base(plan)
        stmt = apply(select(func.count(DocumentChunk.id)))
        return int((await self.session.scalar(stmt)) or 0)

    async def _filtered_search(
        self, query_vector, plan: FilterPlan, top_k: int
    ) -> list[SearchResult]:
        await self.session.execute(
            select(func.set_config("hnsw.ef_search", str(int(settings.hnsw_ef_search)), True))
        )
        apply = self._base(plan)
        distance = DocumentChunk.embedding.cosine_distance(query_vector).label("distance")
        stmt = apply(select(DocumentChunk, distance)).order_by(distance).limit(top_k)
        rows = (await self.session.execute(stmt)).all()
        return [
            SearchResult(
                chunk_id=c.id,
                report_id=c.report_id,
                section_id=c.section_id,
                score=round(1.0 - float(dist), 6),
                chunk_text=c.chunk_text,
                metadata=c.chunk_metadata or {},
            )
            for c, dist in rows
        ]

    async def run(
        self,
        query: str,
        context: RetrievalContext,
        *,
        top_k: int | None = None,
        profile: str | None = None,
    ) -> HybridOutcome:
        prof = get_profile(profile)
        context.validate()                 # pure validation (ranges/enum/taxonomy/self-conflict)
        await self._validate_db(context)   # existence + cross-row consistency
        k = self._resolve_top_k(top_k, prof)
        plan = build_filter_plan(context, preferred_sections=prof.preferred_sections)

        t0 = time.monotonic()
        try:
            vector, stats = await run_in_threadpool(self.query_embedder.embed, query)
            t1 = time.monotonic()
            candidate_count = await self._candidate_count(plan)   # Step 2: candidate selection
            t2 = time.monotonic()
            results = await self._filtered_search(vector, plan, k)  # Step 3: vector search
            t3 = time.monotonic()
        except Exception as exc:  # noqa: BLE001 - log + re-raise for the envelope
            log.error("hybrid.error", error=f"{type(exc).__name__}: {exc}")
            raise

        timings = HybridTimings(
            embedding_ms=round((t1 - t0) * 1000, 2),
            filter_ms=round((t2 - t1) * 1000, 2),
            vector_search_ms=round((t3 - t2) * 1000, 2),
            total_ms=round((t3 - t0) * 1000, 2),
        )
        log.info(
            "hybrid.complete",
            profile=prof.name,
            top_k=k,
            candidate_count=candidate_count,
            returned=len(results),
            filters=plan.applied,
            top_score=results[0].score if results else None,
            **timings.as_dict(),
        )
        return HybridOutcome(
            results=results,
            timings=timings,
            candidate_count=candidate_count,
            applied_filters=plan.applied,
            profile=prof,
            top_k=k,
            query_embedding=stats,
        )
