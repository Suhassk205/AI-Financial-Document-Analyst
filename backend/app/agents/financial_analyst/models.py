"""JSON Schemas and Pydantic models for structured Gemini outputs (Phase 7).

Defines schema interfaces for intent classification, planner steps, and final response models.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field

# Pydantic models for python usage
class IntentResponse(BaseModel):
    intent: str
    confidence: float
    reasoning: str


class PlanStep(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class PlanResponse(BaseModel):
    steps: list[PlanStep]


class Citation(BaseModel):
    source_text: str
    citation_id: str | None = None
    page_number: int | None = None
    section_name: str | None = None


class AgentResponse(BaseModel):
    answer: str
    key_findings: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


# Dict JSON schemas for Google GenAI SDK types.GenerateContentConfig
_INTENT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "intent": {
            "type": "STRING",
            "enum": [
                "RAG_RETRIEVAL",
                "METRIC_EXTRACTION",
                "PERIOD_COMPARISON",
                "RISK_ANALYSIS",
                "TONE_ANALYSIS",
                "HEALTH_CHECK",
                "GENERAL_QA",
            ],
        },
        "confidence": {"type": "NUMBER"},
        "reasoning": {"type": "STRING"},
    },
    "required": ["intent", "confidence", "reasoning"],
}

_PLAN_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "steps": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "tool_name": {
                        "type": "STRING",
                        "enum": [
                            "get_financial_metrics",
                            "get_metric_comparisons",
                            "get_financial_analytics",
                            "get_risk_factors",
                            "get_risk_evolution",
                            "get_management_tone",
                            "get_tone_evolution",
                            "retrieve_evidence",
                        ],
                    },
                    "arguments": {
                        "type": "OBJECT",
                        "description": "Key-value pairs matching tool parameters. company_id and report_id should be UUID strings or null.",
                    },
                },
                "required": ["tool_name", "arguments"],
            },
        }
    },
    "required": ["steps"],
}

_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "answer": {"type": "STRING"},
        "key_findings": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
        "citations": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "source_text": {"type": "STRING"},
                    "citation_id": {"type": "STRING"},
                    "page_number": {"type": "INTEGER"},
                    "section_name": {"type": "STRING"},
                },
                "required": ["source_text"],
            },
        },
    },
    "required": ["answer", "key_findings", "citations"],
}
