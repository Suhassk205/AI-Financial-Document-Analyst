"""State schema for LangGraph agent (Phase 7).

Defines the structure of context and data passed between graph nodes.
"""

from __future__ import annotations

import uuid
from typing import Any, TypedDict


class AgentState(TypedDict):
    """LangGraph State representation for the Financial Analyst agent."""
    query: str
    company_id: uuid.UUID | None
    thread_id: str
    history: list[dict[str, str]]
    
    # Intent / Planning
    intent: str | None
    plan: list[dict[str, Any]] | None
    
    # Execution
    tool_outputs: list[dict[str, Any]]
    
    # Synthesis
    fused_evidence: str | None
    
    # Response
    answer: str | None
    key_findings: list[str] | None
    citations: list[dict[str, Any]] | None
    
    # Diagnostic / Fault Tolerance
    errors: list[str]
