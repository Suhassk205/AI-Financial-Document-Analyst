"""Custom agent-related exceptions (Phase 7).

Ensures type safety and descriptive error handling during graph execution.
"""

from __future__ import annotations


class AgentException(Exception):
    """Base exception for all agent-related failures."""
    pass


class IntentClassificationException(AgentException):
    """Failed to classify query intent."""
    pass


class PlannerException(AgentException):
    """Failed to build a logical execution plan."""
    pass


class ToolExecutionException(AgentException):
    """Failed during tool orchestration / execution."""
    pass


class EvidenceFusionException(AgentException):
    """Failed to synthesize retrieved evidence."""
    pass


class ResponseGenerationException(AgentException):
    """Failed to generate the final response."""
    pass
