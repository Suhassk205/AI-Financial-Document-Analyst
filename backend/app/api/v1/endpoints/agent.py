"""Agent REST APIs (Phase 7).

Exposes chat invocation, thread creation, list, and historical message lookup.
"""

from __future__ import annotations

import uuid
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.repositories.conversation_repository import ConversationRepository
from app.agents.financial_analyst.agent import run_financial_agent
from app.schemas.agent import (
    ChatRequest,
    ChatResponse,
    CitationOut,
    ThreadCreate,
    ThreadOut,
    MessageOut,
)

router = APIRouter()


@router.post(
    "/threads",
    response_model=ThreadOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new conversation thread session",
)
async def create_thread(
    payload: ThreadCreate,
    db: AsyncSession = Depends(get_db),
) -> ThreadOut:
    repo = ConversationRepository(db)
    business_id = f"thread_{uuid.uuid4().hex[:12]}"
    thread = await repo.create_thread(thread_id=business_id, company_id=payload.company_id)
    return ThreadOut(
        id=thread.id,
        thread_id=thread.thread_id,
        company_id=thread.company_id,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


@router.get(
    "/threads",
    response_model=list[ThreadOut],
    summary="List all conversation threads",
)
async def list_threads(
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[ThreadOut]:
    repo = ConversationRepository(db)
    threads = await repo.list_threads(limit=limit, offset=offset)
    return [
        ThreadOut(
            id=t.id,
            thread_id=t.thread_id,
            company_id=t.company_id,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )
        for t in threads
    ]


@router.get(
    "/threads/{thread_id}",
    response_model=ThreadOut,
    summary="Get details of a specific conversation thread",
)
async def get_thread(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
) -> ThreadOut:
    repo = ConversationRepository(db)
    # Search by public business ID
    thread = await repo.get_thread_by_business_id(thread_id)
    if not thread:
        # Fallback search by UUID
        try:
            thread_uuid = uuid.UUID(thread_id)
            thread = await repo.get_thread_by_uuid(thread_uuid)
        except ValueError:
            pass
            
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thread '{thread_id}' not found.",
        )
        
    return ThreadOut(
        id=thread.id,
        thread_id=thread.thread_id,
        company_id=thread.company_id,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


@router.get(
    "/threads/{thread_id}/messages",
    response_model=list[MessageOut],
    summary="Get all historical messages inside a thread",
)
async def get_thread_messages(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[MessageOut]:
    repo = ConversationRepository(db)
    
    # Resolve thread
    thread = await repo.get_thread_by_business_id(thread_id)
    if not thread:
        try:
            thread_uuid = uuid.UUID(thread_id)
            thread = await repo.get_thread_by_uuid(thread_uuid)
        except ValueError:
            pass
            
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thread '{thread_id}' not found.",
        )

    messages = await repo.get_messages_for_thread(thread.id)
    return [
        MessageOut(
            id=m.id,
            thread_id=m.thread_id,
            role=m.role,
            content=m.content,
            created_at=m.created_at,
            metadata=m.message_metadata,
        )
        for m in messages
    ]


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Send a message to the financial analyst agent",
)
async def agent_chat(
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    repo = ConversationRepository(db)
    
    # 1. Resolve or create thread
    thread = await repo.get_thread_by_business_id(payload.thread_id)
    if not thread:
        # Check if they passed a UUID
        try:
            thread_uuid = uuid.UUID(payload.thread_id)
            thread = await repo.get_thread_by_uuid(thread_uuid)
        except ValueError:
            pass

    if not thread:
        # Create a new thread using the requested business ID
        thread = await repo.create_thread(
            thread_id=payload.thread_id,
            company_id=payload.company_id,
        )
    elif payload.company_id and thread.company_id != payload.company_id:
        # Update thread's company if a new one is requested
        thread.company_id = payload.company_id
        db.add(thread)
        await db.commit()

    # 2. Get history
    db_messages = await repo.get_messages_for_thread(thread.id)
    history = [
        {"role": m.role, "content": m.content}
        for m in db_messages
    ]

    # 3. Add user message to DB first
    user_msg = await repo.add_message(
        thread_uuid=thread.id,
        role="user",
        content=payload.query,
    )

    # 4. Run the Agent
    state_out = await run_financial_agent(
        db=db,
        query=payload.query,
        thread_id=thread.thread_id,
        company_id=thread.company_id,
        history=history,
    )

    # 5. Extract results
    answer = state_out.get("answer") or "I could not formulate an answer."
    key_findings = state_out.get("key_findings") or []
    citations = state_out.get("citations") or []

    # 6. Add assistant response to DB
    assistant_metadata = {
        "key_findings": key_findings,
        "citations": citations,
        "intent": state_out.get("intent"),
    }
    
    await repo.add_message(
        thread_uuid=thread.id,
        role="assistant",
        content=answer,
        metadata=assistant_metadata,
    )

    # 7. Map citations to output schema
    citations_out = [
        CitationOut(
            source_text=c.get("source_text"),
            citation_id=c.get("citation_id"),
            page_number=c.get("page_number"),
            section_name=c.get("section_name"),
        )
        for c in citations
    ]

    return ChatResponse(
        answer=answer,
        key_findings=key_findings,
        citations=citations_out,
    )
