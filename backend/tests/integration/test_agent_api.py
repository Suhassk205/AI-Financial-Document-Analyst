"""Integration tests for Phase 7 Financial Analyst Agent API and database layers."""

from __future__ import annotations

import json
import uuid
import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.company import Company
from app.models.conversation_thread import ConversationThread
from app.models.conversation_message import ConversationMessage

PREFIX = settings.api_v1_prefix


def _seed_company(session: Session) -> uuid.UUID:
    """Seed a test company for contextual conversations."""
    company = Company(
        name="Agent Test Company",
        ticker="ATC",
        sector="Financials",
        industry="Asset Management",
    )
    session.add(company)
    session.commit()
    session.refresh(company)
    return company.id


@pytest.mark.integration
async def test_agent_thread_lifecycle(api_client: AsyncClient, sync_session: Session) -> None:
    """Verify threads can be created, listed, and fetched by ID."""
    company_id = _seed_company(sync_session)

    # 1. Create a thread
    resp = await api_client.post(
        f"{PREFIX}/agent/threads",
        json={"company_id": str(company_id)},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert "thread_id" in data
    assert data["company_id"] == str(company_id)

    thread_uuid = data["id"]
    thread_business_id = data["thread_id"]

    # 2. Get thread details by public business ID
    resp_get = await api_client.get(f"{PREFIX}/agent/threads/{thread_business_id}")
    assert resp_get.status_code == 200
    assert resp_get.json()["id"] == thread_uuid

    # 3. List threads
    resp_list = await api_client.get(f"{PREFIX}/agent/threads")
    assert resp_list.status_code == 200
    threads = resp_list.json()
    assert len(threads) >= 1
    assert any(t["id"] == thread_uuid for t in threads)


@pytest.mark.integration
@patch("app.agents.financial_analyst.planner.QueryClassifier._get_client")
@patch("app.agents.financial_analyst.planner.Planner._get_client")
@patch("app.agents.financial_analyst.response_generator.ResponseGenerator._get_client")
@patch("app.agents.tools.retrieval_tools.AdvancedRAGService")
async def test_agent_chat_and_history(
    mock_rag_class: MagicMock,
    mock_generator_client_getter: MagicMock,
    mock_planner_client_getter: MagicMock,
    mock_classifier_client_getter: MagicMock,
    api_client: AsyncClient,
    sync_session: Session,
) -> None:
    """Verify chat endpoint triggers graph, executes tools, and saves history."""
    company_id = _seed_company(sync_session)

    # Mock AdvancedRAGService.retrieve to return predefined context
    mock_rag_instance = MagicMock()
    mock_rag_instance.retrieve.return_value = {
        "context_text": "Sample source evidence text.",
        "citations": [
            {
                "citation_id": "cit_1",
                "section_name": "MD&A",
                "page_number": 1,
                "source_text_preview": "source evidence text"
            }
        ]
    }
    mock_rag_class.return_value = mock_rag_instance

    # Mock Gemini Clients
    mock_client = MagicMock()
    
    # 1st call: Intent classification (RAG_RETRIEVAL)
    intent_resp = MagicMock()
    intent_resp.text = '{"intent": "RAG_RETRIEVAL", "confidence": 0.95, "reasoning": "Wants document details."}'

    # 2nd call: Planner (calls retrieve_evidence tool)
    plan_resp = MagicMock()
    plan_resp.text = json.dumps({
        "steps": [
            {
                "tool_name": "retrieve_evidence",
                "arguments": {"query": "What are the latest risk factors?", "top_k": 3}
            }
        ]
    })

    # 3rd call: Response generator
    res_resp = MagicMock()
    res_resp.text = json.dumps({
        "answer": "Grounded answer from document context.",
        "key_findings": ["Key finding 1"],
        "citations": [{"source_text": "source evidence text", "citation_id": "cit_1", "page_number": 1, "section_name": "MD&A"}]
    })

    mock_client.models.generate_content.side_effect = [intent_resp, plan_resp, res_resp]
    
    mock_classifier_client_getter.return_value = mock_client
    mock_planner_client_getter.return_value = mock_client
    mock_generator_client_getter.return_value = mock_client

    # 1. Start a chat session
    thread_id = f"thread_{uuid.uuid4().hex[:12]}"
    
    resp = await api_client.post(
        f"{PREFIX}/agent/chat",
        json={
            "query": "What are the latest risk factors?",
            "thread_id": thread_id,
            "company_id": str(company_id)
        }
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert data["answer"] == "Grounded answer from document context."
    assert "key_findings" in data
    assert len(data["key_findings"]) == 1
    assert data["key_findings"][0] == "Key finding 1"
    assert len(data["citations"]) == 1
    assert data["citations"][0]["citation_id"] == "cit_1"

    # 2. Verify messages are saved in database
    # Lookup thread first
    thread = sync_session.query(ConversationThread).filter_by(thread_id=thread_id).first()
    assert thread is not None
    assert thread.company_id == company_id

    messages = sync_session.query(ConversationMessage).filter_by(thread_id=thread.id).order_by(ConversationMessage.created_at.asc()).all()
    assert len(messages) == 2
    
    # User message
    assert messages[0].role == "user"
    assert messages[0].content == "What are the latest risk factors?"
    
    # Assistant message
    assert messages[1].role == "assistant"
    assert messages[1].content == "Grounded answer from document context."
    assert messages[1].message_metadata["key_findings"] == ["Key finding 1"]
    assert messages[1].message_metadata["intent"] == "RAG_RETRIEVAL"

    # 3. Retrieve history via REST endpoint
    resp_hist = await api_client.get(f"{PREFIX}/agent/threads/{thread_id}/messages")
    assert resp_hist.status_code == 200
    hist = resp_hist.json()
    assert len(hist) == 2
    assert hist[0]["role"] == "user"
    assert hist[1]["role"] == "assistant"
    assert hist[1]["metadata"]["key_findings"] == ["Key finding 1"]
