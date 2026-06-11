"""Conversation Repository (Phase 7).

Manages database operations for conversation threads and individual messages.
"""

from __future__ import annotations

import uuid
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation_thread import ConversationThread
from app.models.conversation_message import ConversationMessage


class ConversationRepository:
    """Handles DB operations for Chat threads and messages."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_thread_by_business_id(self, thread_id: str) -> ConversationThread | None:
        """Find thread by its unique public business identifier."""
        stmt = select(ConversationThread).where(ConversationThread.thread_id == thread_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_thread_by_uuid(self, thread_uuid: uuid.UUID) -> ConversationThread | None:
        """Find thread by internal database UUID."""
        stmt = select(ConversationThread).where(ConversationThread.id == thread_uuid)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_thread(self, thread_id: str, company_id: uuid.UUID | None = None) -> ConversationThread:
        """Create a new conversation thread session."""
        thread = ConversationThread(
            thread_id=thread_id,
            company_id=company_id,
        )
        self.db.add(thread)
        await self.db.commit()
        await self.db.refresh(thread)
        return thread

    async def list_threads(self, limit: int = 100, offset: int = 0) -> list[ConversationThread]:
        """List all conversation threads."""
        stmt = select(ConversationThread).order_by(ConversationThread.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def add_message(
        self,
        thread_uuid: uuid.UUID,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> ConversationMessage:
        """Append a message to an existing conversation thread."""
        msg = ConversationMessage(
            thread_id=thread_uuid,
            role=role,
            content=content,
            message_metadata=metadata or {},
        )
        self.db.add(msg)
        await self.db.commit()
        await self.db.refresh(msg)
        return msg

    async def get_messages_for_thread(self, thread_uuid: uuid.UUID) -> list[ConversationMessage]:
        """Fetch all messages inside a thread, sorted chronologically."""
        stmt = select(ConversationMessage).where(ConversationMessage.thread_id == thread_uuid).order_by(ConversationMessage.created_at.asc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
