"""ConversationThread ORM model (Phase 7).

Maintains thread session context and references the active company.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.conversation_message import ConversationMessage


class ConversationThread(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "conversation_threads"

    company_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
    )
    thread_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
        index=True,
    )

    company: Mapped[Company | None] = relationship()
    messages: Mapped[list[ConversationMessage]] = relationship(
        "ConversationMessage",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.created_at.asc()",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ConversationThread id={self.id} thread_id={self.thread_id} company_id={self.company_id}>"
