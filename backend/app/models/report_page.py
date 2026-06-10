"""ReportPage ORM model — raw extracted text for one PDF page (Phase 1A).

This is the *only* extraction artifact produced in Phase 1A. Sections, chunks,
embeddings, and structured financial intelligence are explicitly out of scope and
belong to later phases.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import UUIDMixin

if TYPE_CHECKING:
    from app.models.report import Report


class ReportPage(UUIDMixin, Base):
    __tablename__ = "report_pages"

    report_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-based
    page_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    report: Mapped["Report"] = relationship(back_populates="pages")

    __table_args__ = (
        UniqueConstraint("report_id", "page_number", name="uq_report_page_number"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<ReportPage report_id={self.report_id} page={self.page_number}>"
