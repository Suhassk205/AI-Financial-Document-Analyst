"""Company ORM model (Phase 1A subset).

Only the fields needed for ingestion are defined now (name, ticker, sector,
industry). Richer fields (cik, currency, ...) from docs/02_DATABASE_DESIGN.md
are added in later phases.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.report import Report


class Company(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    ticker: Mapped[str | None] = mapped_column(String(16), unique=True, nullable=True)
    sector: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry: Mapped[str | None] = mapped_column(Text, nullable=True)

    reports: Mapped[list["Report"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Company id={self.id} ticker={self.ticker!r}>"
