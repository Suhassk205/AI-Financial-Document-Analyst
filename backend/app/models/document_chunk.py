"""DocumentChunk ORM model — a retrieval-ready knowledge chunk (Phase 1C/2A).

Chunks are produced by section-aware recursive chunking of `report_sections`
(Phase 1C). **Phase 2A** adds the embedding columns: a `pgvector` `vector(768)`
holding the Gemini embedding of `chunk_text`, plus operational tracking
(`embedding_status`, `embedding_model`, `embedding_generated_at`).

The embedding dimension (768) was finalized by calling `gemini-embedding-001`
directly and observing its output (native 3072, Matryoshka-truncated to 768 and
re-normalized). See ADR-013 in docs/06_IMPLEMENTATION_ROADMAP.md. **No pgvector
index (HNSW/IVFFlat) is created here — indexing is deferred to Phase 2B.**

Note: the JSONB column is named `metadata` in the database, but the Python
attribute is `chunk_metadata` because `metadata` is reserved by SQLAlchemy's
declarative base.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import UUIDMixin
from app.models.enums import EmbeddingStatus

# Embedding vector width — sourced from the verified `gemini-embedding-001`
# output (see module docstring / ADR-013). Kept as a literal so the DDL/migration
# and ORM agree; `settings.embedding_dim` mirrors it for validation/stats.
EMBEDDING_DIM = 768

if TYPE_CHECKING:
    from app.models.report import Report
    from app.models.report_section import ReportSection


class DocumentChunk(UUIDMixin, Base):
    __tablename__ = "document_chunks"

    report_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("report_sections.id", ondelete="SET NULL"),
        nullable=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-based, per report
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    start_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # DB column "metadata"; attribute renamed to avoid SQLAlchemy's reserved name.
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )

    # ---- Phase 2A: embedding ------------------------------------------------
    # The pgvector column. Nullable: a chunk exists (Phase 1C) before it is
    # embedded (Phase 2A). Width fixed to the verified Gemini dimension.
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=True
    )
    embedding_status: Mapped[EmbeddingStatus] = mapped_column(
        String(16),
        nullable=False,
        default=EmbeddingStatus.PENDING.value,
        server_default=EmbeddingStatus.PENDING.value,
    )
    embedding_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding_generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    report: Mapped[Report] = relationship(back_populates="chunks")
    section: Mapped[ReportSection | None] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("report_id", "chunk_index", name="uq_document_chunks_report_index"),
        CheckConstraint("token_count >= 0", name="ck_document_chunks_token_count"),
        CheckConstraint("chunk_index >= 0", name="ck_document_chunks_index"),
        CheckConstraint(
            "embedding_status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')",
            name="ck_document_chunks_embedding_status",
        ),
        Index("ix_document_chunks_report_id", "report_id"),
        Index("ix_document_chunks_section_id", "section_id"),
        Index("ix_document_chunks_metadata", "metadata", postgresql_using="gin"),
        # Operational index: quickly find chunks still needing embeddings per report.
        # NOTE: this is a plain btree, NOT an ANN (HNSW/IVFFlat) index — vector
        # similarity indexing is deferred to Phase 2B.
        Index("ix_document_chunks_embedding_status", "report_id", "embedding_status"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<DocumentChunk report_id={self.report_id} "
            f"index={self.chunk_index} tokens={self.token_count}>"
        )
