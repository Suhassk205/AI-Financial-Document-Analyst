"""Master Agent Coordinator (Phase 7).

Assembles the LangGraph orchestrator graph and exports the run entrypoint.
"""

from __future__ import annotations

import uuid
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from google import genai
from langgraph.graph import END, START, StateGraph

from app.core.logging import get_logger
from app.agents.financial_analyst.state import AgentState
from app.agents.financial_analyst.planner import QueryClassifier, Planner
from app.agents.financial_analyst.executor import execute_tools_node
from app.agents.financial_analyst.evidence_fusion import EvidenceFusion
from app.agents.financial_analyst.response_generator import ResponseGenerator

log = get_logger(__name__)


def create_financial_agent_graph(client: genai.Client | None = None) -> StateGraph:
    """Build and compile the deterministic LangGraph workflow."""
    classifier = QueryClassifier(client=client)
    planner = Planner(client=client)
    fusion = EvidenceFusion()
    generator = ResponseGenerator(client=client)

    workflow = StateGraph(AgentState)

    # Register nodes
    workflow.add_node("classify_intent", classifier.classify)
    workflow.add_node("planner", planner.build_plan)
    workflow.add_node("executor", execute_tools_node)
    workflow.add_node("evidence_fusion", fusion.fuse_evidence)
    workflow.add_node("response_generator", generator.generate_response)

    # Deterministic sequential routing
    workflow.add_edge(START, "classify_intent")
    workflow.add_edge("classify_intent", "planner")
    workflow.add_edge("planner", "executor")
    workflow.add_edge("executor", "evidence_fusion")
    workflow.add_edge("evidence_fusion", "response_generator")
    workflow.add_edge("response_generator", END)

    return workflow.compile()


# Export a compiled graph instance
financial_agent_graph = create_financial_agent_graph()


async def run_financial_agent(
    db: AsyncSession,
    query: str,
    thread_id: str,
    company_id: uuid.UUID | None = None,
    history: list[dict[str, str]] | None = None,
    client: genai.Client | None = None,
) -> dict[str, Any]:
    """Invoke the Financial Analyst Agent graph.
    
    Args:
        db: Active AsyncSession transaction.
        query: User input query.
        thread_id: Business unique thread identifier.
        company_id: Optional UUID of active company context.
        history: List of conversation messages.
        client: Optional Gemini client to override default.
    """
    state_input: AgentState = {
        "query": query,
        "company_id": company_id,
        "thread_id": thread_id,
        "history": history or [],
        "intent": None,
        "plan": None,
        "tool_outputs": [],
        "fused_evidence": None,
        "answer": None,
        "key_findings": None,
        "citations": None,
        "errors": [],
    }

    # Pass the database session via the configurable config key
    config = {"configurable": {"db": db}}
    
    # Resolve graph (uses client override if passed)
    graph = create_financial_agent_graph(client=client) if client else financial_agent_graph

    log.info("run_financial_agent.start", query=query, thread_id=thread_id, company_id=company_id)
    state_output = await graph.ainvoke(state_input, config=config)
    log.info("run_financial_agent.finish", thread_id=thread_id, success=not bool(state_output.get("errors")))
    
    return state_output
