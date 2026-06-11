"""ConversationMessage ORM model (Phase 7).

Stores individual messages inside a conversation thread.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import UUIDMixin

if TYPE_CHECKING:
    from app.models.conversation_thread import ConversationThread


class ConversationMessage(UUIDMixin, Base):
    __tablename__ = "conversation_messages"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversation_threads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)  # "user", "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # DB column "metadata"; attribute renamed to avoid SQLAlchemy's reserved name.
    message_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    thread: Mapped[ConversationThread] = relationship(
        "ConversationThread",
        back_populates="messages",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ConversationMessage id={self.id} thread_id={self.thread_id} role={self.role}>"
