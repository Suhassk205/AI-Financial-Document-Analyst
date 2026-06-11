"""Unit tests for Financial Analyst Agent (Phase 7).

Verifies nodes, state transitions, validation, and graph workflow with mocked Gemini calls.
"""

from __future__ import annotations

import json
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.financial_analyst.exceptions import (
    AgentException,
    IntentClassificationException,
    PlannerException,
    ToolExecutionException,
    EvidenceFusionException,
    ResponseGenerationException,
)
from app.agents.financial_analyst.validators import (
    validate_intent_classification,
    validate_planning,
    validate_tool_execution,
    validate_evidence_fusion,
    validate_response_generation,
)
from app.agents.financial_analyst.planner import QueryClassifier, Planner
from app.agents.financial_analyst.executor import ToolExecutor
from app.agents.financial_analyst.evidence_fusion import EvidenceFusion
from app.agents.financial_analyst.response_generator import ResponseGenerator
from app.agents.financial_analyst.agent import run_financial_agent


def test_custom_exceptions():
    """Verify agent exceptions hierarchy."""
    with pytest.raises(AgentException):
        raise IntentClassificationException("Intent failed")
        
    with pytest.raises(AgentException):
        raise PlannerException("Plan failed")

    with pytest.raises(AgentException):
        raise ToolExecutionException("Tool failed")


def test_state_validators():
    """Verify validator assertions on invalid states."""
    # Intent classification validator
    with pytest.raises(IntentClassificationException):
        validate_intent_classification({"query": "", "thread_id": "123"})
    with pytest.raises(IntentClassificationException):
        validate_intent_classification({"query": "hello", "thread_id": ""})

    # Planning validator
    with pytest.raises(PlannerException):
        validate_planning({"intent": None})

    # Tool executor validator
    with pytest.raises(ToolExecutionException):
        validate_tool_execution({"plan": None})

    # Evidence fusion validator
    with pytest.raises(EvidenceFusionException):
        validate_evidence_fusion({"intent": None})

    # Response generation validator
    with pytest.raises(ResponseGenerationException):
        validate_response_generation({"query": ""})


@pytest.mark.asyncio
async def test_evidence_fusion_formatting():
    """Verify EvidenceFusion correctly formats tool outputs as markdown."""
    fusion = EvidenceFusion()
    
    # 1. Test empty output
    empty_res = await fusion.fuse_evidence({"tool_outputs": [], "intent": "METRIC_EXTRACTION"})
    assert "No primary evidence" in empty_res["fused_evidence"]
    
    # 2. Test metrics formatting
    metrics_output = {
        "tool_name": "get_financial_metrics",
        "success": True,
        "result": [
            {
                "normalized_metric_name": "Revenue",
                "metric_name": "Total Revenue",
                "value": 1500000.0,
                "currency": "USD",
                "unit": "USD",
                "fiscal_year": 2023,
                "fiscal_quarter": None,
                "metric_category": "INCOME_STATEMENT",
                "confidence_score": 0.95,
            }
        ]
    }
    
    # 3. Test failed tool output
    failed_output = {
        "tool_name": "get_risk_factors",
        "success": False,
        "result": "Database Timeout"
    }

    res = await fusion.fuse_evidence({
        "tool_outputs": [metrics_output, failed_output],
        "intent": "MIXED"
    })
    assert "### Financial Metrics" in res["fused_evidence"]
    assert "Revenue" in res["fused_evidence"]
    assert "USD 1,500,000.0" in res["fused_evidence"]
    assert "### Tool Execution Failure: get_risk_factors" in res["fused_evidence"]
    assert "Database Timeout" in res["fused_evidence"]


@pytest.mark.asyncio
async def test_query_classifier_mock():
    """Verify QueryClassifier returns classified intent using mock Gemini client."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '{"intent": "PERIOD_COMPARISON", "confidence": 0.9, "reasoning": "YoY query"}'
    mock_client.models.generate_content.return_value = mock_response

    classifier = QueryClassifier(client=mock_client)
    state = {"query": "Compare revenue between 2022 and 2023", "thread_id": "t123"}
    
    res = await classifier.classify(state)
    assert res["intent"] == "PERIOD_COMPARISON"
    mock_client.models.generate_content.assert_called_once()


@pytest.mark.asyncio
async def test_planner_mock():
    """Verify Planner builds plans with steps using mock Gemini client."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '{"steps": [{"tool_name": "get_metric_comparisons", "arguments": {"company_id": "123"}}]}'
    mock_client.models.generate_content.return_value = mock_response

    planner = Planner(client=mock_client)
    state = {
        "query": "Compare metrics",
        "intent": "PERIOD_COMPARISON",
        "company_id": uuid.uuid4(),
    }
    
    res = await planner.build_plan(state)
    assert len(res["plan"]) == 1
    assert res["plan"][0]["tool_name"] == "get_metric_comparisons"


@pytest.mark.asyncio
async def test_tool_executor_db_missing():
    """Verify ToolExecutor raises error if DB session is missing."""
    from app.agents.financial_analyst.executor import execute_tools_node
    state = {"plan": [{"tool_name": "get_financial_metrics", "arguments": {}}]}
    
    with pytest.raises(ToolExecutionException):
        await execute_tools_node(state, config={})


@pytest.mark.asyncio
async def test_response_generator_mock():
    """Verify ResponseGenerator outputs structured answers using mock Gemini."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "answer": "The operating margin is 15%.",
        "key_findings": ["Operating margin improved YoY"],
        "citations": [{"source_text": "margin was 15%", "citation_id": "c1", "page_number": 3, "section_name": "MD&A"}]
    })
    mock_client.models.generate_content.return_value = mock_response

    generator = ResponseGenerator(client=mock_client)
    state = {
        "query": "What is the margin?",
        "fused_evidence": "margin was 15%",
        "intent": "RAG_RETRIEVAL"
    }
    
    res = await generator.generate_response(state)
    assert res["answer"] == "The operating margin is 15%."
    assert len(res["key_findings"]) == 1
    assert len(res["citations"]) == 1
    assert res["citations"][0]["citation_id"] == "c1"


@pytest.mark.asyncio
async def test_full_agent_graph_mock():
    """Verify run_financial_agent runs end-to-end with mock clients."""
    mock_client = MagicMock()
    
    # 1. Intent mock response
    intent_resp = MagicMock()
    intent_resp.text = '{"intent": "GENERAL_QA", "confidence": 1.0, "reasoning": "test"}'
    
    # 2. Plan mock response
    plan_resp = MagicMock()
    plan_resp.text = '{"steps": []}'  # empty steps for general QA
    
    # 3. Response mock response
    res_resp = MagicMock()
    res_resp.text = json.dumps({
        "answer": "This is a general greeting.",
        "key_findings": ["Greeting verified"],
        "citations": []
    })
    
    mock_client.models.generate_content.side_effect = [intent_resp, plan_resp, res_resp]

    # Mock Async DB session
    mock_db = MagicMock(spec=AsyncSession)

    res = await run_financial_agent(
        db=mock_db,
        query="Hello agent",
        thread_id="thread_test_123",
        client=mock_client
    )

    assert res["answer"] == "This is a general greeting."
    assert res["intent"] == "GENERAL_QA"
    assert not res.get("errors")
