"""API v1 aggregate router.

Mounts all v1 sub-routers. Today only operational endpoints exist. Business
routers (upload, search, metrics, risks, benchmark, memos, chat, export — see
docs/04_API_DESIGN.md) are added in their respective phases and included here.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import chunks, embeddings, health, reports

api_router = APIRouter()

# Operational endpoints (Phase 0.5).
api_router.include_router(health.router)

# Report ingestion + sections + chunks (Phase 1A/1B/1C).
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(chunks.router, prefix="/chunks", tags=["chunks"])

# Embedding generation + operational monitoring (Phase 2A). Report-scoped paths.
api_router.include_router(embeddings.router, prefix="/reports", tags=["embeddings"])

# --- Business routers (added per phase) ---------------------------------------
# api_router.include_router(search.router,    prefix="/search",    tags=["search"])     # Phase 2B
# api_router.include_router(metrics.router,   prefix="/reports",   tags=["metrics"])    # Phase 3
# api_router.include_router(risks.router,     prefix="/reports",   tags=["risks"])      # Phase 4
# api_router.include_router(benchmark.router, prefix="/benchmark", tags=["benchmark"])  # Phase 8
# api_router.include_router(memos.router,     prefix="/memos",     tags=["memos"])      # Phase 9
# api_router.include_router(chat.router,      prefix="/chat",      tags=["chat"])       # Phase 10
