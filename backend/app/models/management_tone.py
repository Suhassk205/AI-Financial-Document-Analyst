"""ManagementTone ORM model — management tone records (Phase 5).

Stores sentiment, confidence, and hedging metrics extracted from management commentary.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import UUIDMixin

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.report import Report


class ManagementTone(UUIDMixin, Base):
    __tablename__ = "management_tone"

    company_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="SET NULL"),
        nullable=True,
    )

    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    sentiment: Mapped[str] = mapped_column(String(10), nullable=False)
    confidence_level: Mapped[str] = mapped_column(String(20), nullable=False)

    hedging_score: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    positive_score: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    negative_score: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)

    extraction_method: Mapped[str] = mapped_column(String(20), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    company: Mapped["Company"] = relationship()
    report: Mapped["Report"] = relationship()

    __table_args__ = (
        CheckConstraint("hedging_score BETWEEN 0 AND 1", name="ck_management_tone_hedging"),
        CheckConstraint("positive_score BETWEEN 0 AND 1", name="ck_management_tone_positive"),
        CheckConstraint("negative_score BETWEEN 0 AND 1", name="ck_management_tone_negative"),
        CheckConstraint("confidence_score BETWEEN 0 AND 1", name="ck_management_tone_confidence"),
        CheckConstraint(
            "sentiment IN ('POSITIVE', 'NEUTRAL', 'NEGATIVE')",
            name="ck_management_tone_sentiment",
        ),
        CheckConstraint(
            "confidence_level IN ('VERY_CONFIDENT', 'CONFIDENT', 'CAUTIOUS', 'VERY_CAUTIOUS')",
            name="ck_management_tone_confidence_level",
        ),
        CheckConstraint(
            "extraction_method IN ('RULE_BASED', 'LLM_BASED', 'HYBRID_VALIDATED')",
            name="ck_management_tone_method",
        ),
        Index("ix_management_tone_company_id", "company_id"),
        Index("ix_management_tone_report_id", "report_id"),
        Index("ix_management_tone_source_chunk_id", "source_chunk_id"),
        Index("ix_management_tone_sentiment", "sentiment"),
        Index("ix_management_tone_confidence_level", "confidence_level"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ManagementTone sentiment={self.sentiment} "
            f"confidence_level={self.confidence_level} report={self.report_id}>"
        )
