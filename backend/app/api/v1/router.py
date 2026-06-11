"""API v1 aggregate router.

Mounts all v1 sub-routers. Today only operational endpoints exist. Business
routers (upload, search, metrics, risks, benchmark, memos, chat, export — see
docs/04_API_DESIGN.md) are added in their respective phases and included here.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import (
    analytics,
    chunks,
    comparisons,
    embeddings,
    evaluation,
    health,
    metrics,
    reports,
    risks,
    search,
    tone,
    rag,
    agent,
)

api_router = APIRouter()

# Operational endpoints (Phase 0.5).
api_router.include_router(health.router)

# Report ingestion + sections + chunks (Phase 1A/1B/1C).
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(chunks.router, prefix="/chunks", tags=["chunks"])

# Embedding generation + operational monitoring (Phase 2A). Report-scoped paths.
api_router.include_router(embeddings.router, prefix="/reports", tags=["embeddings"])

# Vector + hybrid search (Phase 2B/2C) — retrieval only, no reasoning.
api_router.include_router(search.router, prefix="/search", tags=["search"])

# Retrieval evaluation & observability (Phase 2D) — measurement only.
api_router.include_router(evaluation.router, prefix="/evaluation", tags=["evaluation"])

# Financial metric extraction (Phase 3A) — report-scoped; inspection + trigger.
api_router.include_router(metrics.router, prefix="/reports", tags=["metrics"])

# Period comparisons (Phase 3B) — report + company scoped; full paths inside.
api_router.include_router(comparisons.router, tags=["comparisons"])

# Financial analytics (Phase 3C) — report + company scoped; full paths inside.
api_router.include_router(analytics.router, tags=["analytics"])

# Risk intelligence (Phase 4) — report + company scoped; full paths inside.
api_router.include_router(risks.router, tags=["risks"])

# Management tone intelligence (Phase 5) — report + company scoped; full paths inside.
api_router.include_router(tone.router, tags=["tone"])

# Advanced Retrieval & RAG (Phase 6)
api_router.include_router(rag.router, prefix="/rag", tags=["rag"])

# Financial Analyst Agent System (Phase 7)
api_router.include_router(agent.router, prefix="/agent", tags=["agent"])

# --- Business routers (added per phase) ---------------------------------------
# api_router.include_router(benchmark.router, prefix="/benchmark", tags=["benchmark"])  # Phase 8
# api_router.include_router(memos.router,     prefix="/memos",     tags=["memos"])      # Phase 9
# api_router.include_router(chat.router,      prefix="/chat",      tags=["chat"])       # Phase 10
