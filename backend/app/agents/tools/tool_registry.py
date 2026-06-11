"""Tool registry for Agent system (Phase 7).

Declares all allowed tools and enables execution mapping.
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.financial_tools import (
    get_financial_metrics,
    get_metric_comparisons,
    get_financial_analytics,
)
from app.agents.tools.risk_tools import get_risk_factors, get_risk_evolution
from app.agents.tools.tone_tools import get_management_tone, get_tone_evolution
from app.agents.tools.retrieval_tools import retrieve_evidence

# Registry mapping tool name strings to their coroutine functions
TOOL_REGISTRY: dict[str, Callable[..., Coroutine[Any, Any, Any]]] = {
    "get_financial_metrics": get_financial_metrics,
    "get_metric_comparisons": get_metric_comparisons,
    "get_financial_analytics": get_financial_analytics,
    "get_risk_factors": get_risk_factors,
    "get_risk_evolution": get_risk_evolution,
    "get_management_tone": get_management_tone,
    "get_tone_evolution": get_tone_evolution,
    "retrieve_evidence": retrieve_evidence,
}
