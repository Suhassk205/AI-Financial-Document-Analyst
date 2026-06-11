"""Response Generator node (Phase 7).

Assembles the final structured output from the user query and fused evidence.
"""

from __future__ import annotations

import json
from typing import Any

from google import genai
from google.genai import types

from app.core.config import settings
from app.core.logging import get_logger
from app.agents.financial_analyst.state import AgentState
from app.agents.financial_analyst.validators import validate_response_generation
from app.agents.financial_analyst.models import _RESPONSE_SCHEMA

log = get_logger(__name__)


class ResponseGenerator:
    """Generates the final structured response using Gemini."""

    def __init__(self, client: genai.Client | None = None) -> None:
        self.api_key = settings.gemini_api_key
        self._client = client
        self.model = settings.gemini_llm_model

    def _get_client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def generate_response(self, state: AgentState) -> dict[str, Any]:
        """Generate the final grounded response using Gemini."""
        validate_response_generation(state)
        query = state["query"]
        fused_evidence = state.get("fused_evidence") or "No evidence retrieved."
        history = state.get("history") or []

        history_str = "\n".join(
            [f"{msg['role'].upper()}: {msg['content']}" for msg in history]
        )

        prompt = (
            "You are a professional Financial Analyst. Generate a detailed, grounded response to the user query.\n"
            "Strictly base your response on the provided Fused Evidence. Do not make up facts or metrics. "
            "If the Fused Evidence does not contain the answer, explain what is missing instead of hallucinating.\n\n"
            "IMPORTANT RULES:\n"
            "1. NEVER make any buy/sell/hold investment recommendations or price target projections. Maintain objective, analytical tone.\n"
            "2. For every claim, statistic, or metric cited, link it to the Fused Evidence and provide precise citations in the structured output.\n"
            "3. Format the final output as a JSON object matching the requested schema.\n\n"
            f"Conversation History:\n{history_str}\n\n"
            f"Fused Evidence Context:\n{fused_evidence}\n\n"
            f"USER QUERY: \"{query}\"\n"
        )

        try:
            client = self._get_client()
            resp = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_RESPONSE_SCHEMA,
                    temperature=0.1,
                ),
            )
            raw_text = resp.text or "{}"
            data = json.loads(raw_text)
            
            return {
                "answer": data.get("answer", ""),
                "key_findings": data.get("key_findings", []),
                "citations": data.get("citations", []),
            }
        except Exception as exc:
            log.error("response_generator.error", error=str(exc))
            # Safe fallback response in case of API failure or schema mismatch
            fallback_answer = (
                "I apologize, but I encountered an error generating the final response. "
                "Here is the raw evidence collected for your query:\n\n" + fused_evidence
            )
            return {
                "answer": fallback_answer,
                "key_findings": ["Error during response generation."],
                "citations": [],
                "errors": state.get("errors", []) + [f"Response generation error: {exc}"]
            }
