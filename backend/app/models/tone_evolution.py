"""ToneEvolution ORM model — period-over-period management tone changes (Phase 5).

Tracks how management tone evolves across sequential reporting periods.
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
    from app.models.management_tone import ManagementTone


class ToneEvolution(UUIDMixin, Base):
    __tablename__ = "tone_evolution"

    company_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    current_tone_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("management_tone.id", ondelete="CASCADE"),
        nullable=True,
    )
    previous_tone_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("management_tone.id", ondelete="CASCADE"),
        nullable=True,
    )

    evolution_type: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    company: Mapped["Company"] = relationship()
    current_tone: Mapped["ManagementTone | None"] = relationship(foreign_keys=[current_tone_id])
    previous_tone: Mapped["ManagementTone | None"] = relationship(foreign_keys=[previous_tone_id])

    __table_args__ = (
        CheckConstraint("confidence_score BETWEEN 0 AND 1", name="ck_tone_evolution_confidence"),
        CheckConstraint(
            "evolution_type IN ('MORE_POSITIVE', 'MORE_NEGATIVE', 'MORE_CONFIDENT', 'LESS_CONFIDENT', 'MORE_CAUTIOUS', 'LESS_CAUTIOUS', 'UNCHANGED')",
            name="ck_tone_evolution_type",
        ),
        Index("ix_tone_evolution_company_id", "company_id"),
        Index("ix_tone_evolution_current_tone_id", "current_tone_id"),
        Index("ix_tone_evolution_previous_tone_id", "previous_tone_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ToneEvolution type={self.evolution_type} "
            f"current={self.current_tone_id} previous={self.previous_tone_id}>"
        )
