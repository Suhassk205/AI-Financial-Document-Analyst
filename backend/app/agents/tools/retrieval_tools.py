"""Retrieval tools for Agent system (Phase 7).

Provides functions to access Advanced RAG and search capabilities.
"""

from __future__ import annotations

import uuid
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.service import AdvancedRAGService
from app.retrieval.hybrid import RetrievalContext


async def retrieve_evidence(
    db: AsyncSession,
    query: str,
    company_id: uuid.UUID | None = None,
    report_id: uuid.UUID | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    """Retrieve grounded evidence using Phase 6 Advanced RAG service."""
    service = AdvancedRAGService(db)
    
    # Map filters to RetrievalContext
    context = RetrievalContext(
        company_id=company_id,
        report_id=report_id,
    )
    
    context_pkg, steps, _, _ = await service.retrieve_and_assemble(
        query=query,
        context=context,
        top_k=top_k,
    )
    
    return {
        "context_text": context_pkg.context_text,
        "tokens_used": context_pkg.tokens_used,
        "budget_limit": context_pkg.budget_limit,
        "citations": [
            {
                "citation_id": c.citation_id,
                "report_id": str(c.report_id),
                "chunk_id": str(c.chunk_id),
                "page_number": c.page_number,
                "section_name": c.section_name,
                "source_text_preview": c.source_text_preview,
            }
            for c in context_pkg.citations
        ],
        "steps": steps,
    }
