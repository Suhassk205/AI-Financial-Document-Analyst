"""Tool Executor node (Phase 7).

Orchestrates tool executions, passes active DB sessions, and aggregates results.
"""

import uuid
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.runnables import RunnableConfig

from app.core.logging import get_logger
from app.agents.financial_analyst.state import AgentState
from app.agents.financial_analyst.exceptions import ToolExecutionException
from app.agents.financial_analyst.validators import validate_tool_execution
from app.agents.tools.tool_registry import TOOL_REGISTRY

log = get_logger(__name__)


class ToolExecutor:
    """Orchestrates tool execution inside the agent workflow."""

    async def execute_tools(self, state: AgentState, db: AsyncSession) -> dict[str, Any]:
        """Execute each step in the plan using the registry tools."""
        validate_tool_execution(state)
        plan = state["plan"] or []

        outputs = []
        errors = list(state.get("errors", []))

        for step in plan:
            tool_name = step.get("tool_name")
            arguments = step.get("arguments") or {}

            if tool_name not in TOOL_REGISTRY:
                err_msg = f"Tool '{tool_name}' not found in TOOL_REGISTRY."
                log.error("tool_executor.missing_tool", tool_name=tool_name)
                errors.append(err_msg)
                continue

            tool_func = TOOL_REGISTRY[tool_name]

            # Convert ID strings to UUIDs
            sanitized_args = {}
            for k, v in arguments.items():
                if k in ("company_id", "report_id") and isinstance(v, str) and v.strip():
                    try:
                        sanitized_args[k] = uuid.UUID(v)
                    except ValueError:
                        sanitized_args[k] = v
                else:
                    sanitized_args[k] = v

            try:
                log.info("tool_executor.executing", tool_name=tool_name, args=sanitized_args)
                result = await tool_func(db, **sanitized_args)
                outputs.append({
                    "tool_name": tool_name,
                    "input_arguments": arguments,
                    "result": result,
                    "success": True
                })
            except Exception as exc:
                err_msg = f"Error executing tool '{tool_name}': {exc}"
                log.error("tool_executor.failure", tool_name=tool_name, error=str(exc))
                errors.append(err_msg)
                outputs.append({
                    "tool_name": tool_name,
                    "input_arguments": arguments,
                    "result": str(exc),
                    "success": False
                })

        return {"tool_outputs": outputs, "errors": errors}


async def execute_tools_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """LangGraph node wrapper for ToolExecutor."""
    db: AsyncSession | None = None
    if config and "configurable" in config:
        db = config["configurable"].get("db")

    if db is None:
        raise ToolExecutionException("Active database session 'db' was not provided in graph config.")

    executor = ToolExecutor()
    return await executor.execute_tools(state, db)
