"""State validation helpers (Phase 7).

Provides runtime assertions to verify correct transitions between graph nodes.
"""

from __future__ import annotations

from app.agents.financial_analyst.state import AgentState
from app.agents.financial_analyst.exceptions import (
    IntentClassificationException,
    PlannerException,
    ToolExecutionException,
    EvidenceFusionException,
    ResponseGenerationException,
)


def validate_intent_classification(state: AgentState) -> None:
    """Pre-node validation for Intent Classification."""
    if not state.get("query"):
        raise IntentClassificationException("Missing required query in state.")
    if not state.get("thread_id"):
        raise IntentClassificationException("Missing thread_id in state.")


def validate_planning(state: AgentState) -> None:
    """Pre-node validation for Planning."""
    if not state.get("intent"):
        raise PlannerException("State must have a classified intent before planning.")


def validate_tool_execution(state: AgentState) -> None:
    """Pre-node validation for Tool Execution."""
    if state.get("plan") is None:
        raise ToolExecutionException("State must contain an execution plan before executing tools.")


def validate_evidence_fusion(state: AgentState) -> None:
    """Pre-node validation for Evidence Fusion."""
    # Even if tool outputs are empty, we allow fusion to run, but we validate state completeness
    if state.get("intent") is None:
        raise EvidenceFusionException("State must have intent to perform evidence fusion.")


def validate_response_generation(state: AgentState) -> None:
    """Pre-node validation for Response Generation."""
    # We must have a query to generate response
    if not state.get("query"):
        raise ResponseGenerationException("Missing query for response generation.")
