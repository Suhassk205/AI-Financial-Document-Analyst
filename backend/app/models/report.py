"""Report ORM model — one uploaded financial document (Phase 1A)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import UUIDMixin
from app.models.enums import ReportStatus, ReportType

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.report_page import ReportPage


class Report(UUIDMixin, Base):
    __tablename__ = "reports"

    company_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Enums stored as VARCHAR + CHECK (native_enum=False) — no PG ENUM type, so
    # values evolve via simple migrations (see docs/02_DATABASE_DESIGN.md §3).
    report_type: Mapped[ReportType] = mapped_column(
        SQLEnum(ReportType, native_enum=False, length=16, name="report_type", validate_strings=True),
        nullable=False,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter: Mapped[int | None] = mapped_column(Integer, nullable=True)

    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[ReportStatus] = mapped_column(
        SQLEnum(
            ReportStatus, native_enum=False, length=16, name="report_status", validate_strings=True
        ),
        nullable=False,
        default=ReportStatus.UPLOADED,
        server_default=ReportStatus.UPLOADED.value,
    )
    total_pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processing_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    company: Mapped["Company | None"] = relationship(back_populates="reports")
    pages: Mapped[list["ReportPage"]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ReportPage.page_number",
    )

    __table_args__ = (
        CheckConstraint("quarter IS NULL OR (quarter BETWEEN 1 AND 4)", name="quarter_range"),
        CheckConstraint("year BETWEEN 1900 AND 2200", name="year_range"),
        CheckConstraint("total_pages IS NULL OR total_pages >= 0", name="total_pages_nonneg"),
        Index("ix_reports_company_id", "company_id"),
        Index("ix_reports_status", "status"),
        Index("ix_reports_uploaded_at", "uploaded_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Report id={self.id} type={self.report_type} status={self.status}>"
