"""LLM-assisted management tone analyzer (Phase 5)."""

from __future__ import annotations

import json
import time
from collections.abc import Callable

from app.core.config import settings as app_settings
from app.core.logging import get_logger
from app.models.enums import Sentiment, ConfidenceLevel
from app.tone.analysis.exceptions import (
    ToneLLMError,
    ToneLLMResponseError,
    ToneLLMTransientError,
)
from app.tone.analysis.models import ToneCandidate, ToneChunkInput

log = get_logger(__name__)

_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "sentiment": {
            "type": "STRING",
            "enum": ["POSITIVE", "NEUTRAL", "NEGATIVE"],
        },
        "confidence_level": {
            "type": "STRING",
            "enum": ["VERY_CONFIDENT", "CONFIDENT", "CAUTIOUS", "VERY_CAUTIOUS"],
        },
        "hedging_strength": {"type": "NUMBER"},
        "positive_strength": {"type": "NUMBER"},
        "negative_strength": {"type": "NUMBER"},
        "confidence": {"type": "NUMBER"},
    },
    "required": ["sentiment", "confidence_level", "hedging_strength", "confidence"],
}


class LLMBasedToneAnalyzer:
    """Analyzes tone using Gemini 2.5 Pro with structured output JSON schema."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_retries: int = 3,
        base_delay: float = 2.0,
        timeout: float = 60.0,
        client: object | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._timeout = timeout
        self._client = client
        self._sleep = sleep

    @classmethod
    def from_settings(cls, *, client: object | None = None) -> LLMBasedToneAnalyzer:
        return cls(
            api_key=app_settings.gemini_api_key,
            model=app_settings.gemini_llm_model,
            max_retries=app_settings.metric_llm_max_retries,
            base_delay=app_settings.metric_llm_retry_base_delay,
            timeout=app_settings.metric_llm_request_timeout,
            client=client,
        )

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    def analyze_chunk(self, chunk: ToneChunkInput) -> ToneCandidate | None:
        if not self.enabled:
            log.warning("tone_extraction.llm_disabled", reason="no GEMINI_API_KEY; rule-only")
            return None

        try:
            raw = self._with_retries(lambda text=chunk.text: self._generate(text))
            return self._parse(raw, chunk)
        except ToneLLMError as exc:
            log.error("tone_extraction.llm_chunk_failed", chunk_id=chunk.chunk_id, error=str(exc))
            return None

    def _build_prompt(self, text: str) -> str:
        return (
            "Analyze the sentiment, confidence level, and hedging (uncertainty) strength of the following management commentary text.\n"
            "Sentiment must be one of: POSITIVE, NEUTRAL, NEGATIVE.\n"
            "Confidence Level must be one of: VERY_CONFIDENT, CONFIDENT, CAUTIOUS, VERY_CAUTIOUS.\n"
            "Provide numerical strengths/scores between 0.0 and 1.0 for hedging_strength, positive_strength, and negative_strength.\n"
            "Include a self-assessed confidence score between 0.0 and 1.0 for this classification.\n\n"
            f"TEXT:\n{text}"
        )

    def _get_client(self) -> object:
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def _generate(self, text: str) -> str:
        from google.genai import types

        client = self._get_client()
        try:
            resp = client.models.generate_content(  # type: ignore[attr-defined]
                model=self._model,
                contents=self._build_prompt(text),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_RESPONSE_SCHEMA,
                    temperature=0.0,
                ),
            )
        except Exception as exc:
            raise self._classify(exc) from exc
        return resp.text or "{}"

    def _with_retries(self, call: Callable[[], str]) -> str:
        attempt = 0
        while True:
            try:
                return call()
            except ToneLLMError as exc:
                if not getattr(exc, "retryable", False) or attempt >= self._max_retries:
                    raise
                delay = self._base_delay * (2**attempt)
                attempt += 1
                log.warning("tone_extraction.llm_retry", attempt=attempt, error=str(exc))
                self._sleep(delay)

    @staticmethod
    def _classify(exc: Exception) -> ToneLLMError:
        msg = str(exc).lower()
        code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        if code == 429 or "rate limit" in msg or "resource_exhausted" in msg or "quota" in msg:
            return ToneLLMTransientError(str(exc))
        if (isinstance(code, int) and code >= 500) or "timeout" in msg or "unavailable" in msg:
            return ToneLLMTransientError(str(exc))
        return ToneLLMError(str(exc))

    def _parse(self, raw: str, ch: ToneChunkInput) -> ToneCandidate | None:
        try:
            item = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ToneLLMResponseError(f"invalid JSON from LLM: {exc}") from exc

        if not isinstance(item, dict):
            raise ToneLLMResponseError("LLM response is not a JSON object")

        try:
            sentiment_str = str(item.get("sentiment", "NEUTRAL")).upper().strip()
            sentiment = Sentiment(sentiment_str)
        except ValueError:
            sentiment = Sentiment.NEUTRAL

        try:
            conf_level_str = str(item.get("confidence_level", "CONFIDENT")).upper().strip()
            confidence_level = ConfidenceLevel(conf_level_str)
        except ValueError:
            confidence_level = ConfidenceLevel.CONFIDENT

        try:
            hedging_score = max(0.0, min(1.0, float(item.get("hedging_strength", 0.0))))
        except (TypeError, ValueError):
            hedging_score = 0.0

        try:
            positive_score = max(0.0, min(1.0, float(item.get("positive_strength", 0.0))))
        except (TypeError, ValueError):
            positive_score = 0.0

        try:
            negative_score = max(0.0, min(1.0, float(item.get("negative_strength", 0.0))))
        except (TypeError, ValueError):
            negative_score = 0.0

        try:
            confidence_score = max(0.0, min(1.0, float(item.get("confidence", 0.8))))
        except (TypeError, ValueError):
            confidence_score = 0.8

        source_type = ch.normalized_section_name or "Management Commentary"

        return ToneCandidate(
            source_chunk_id=ch.chunk_id,
            source_type=source_type,
            sentiment=sentiment,
            confidence_level=confidence_level,
            hedging_score=hedging_score,
            positive_score=positive_score,
            negative_score=negative_score,
            confidence_score=confidence_score,
            source_text=ch.text[:300].strip(),
            extraction_method="LLM_BASED",
            extraction_metadata={
                "llm_sentiment": item.get("sentiment"),
                "llm_confidence_level": item.get("confidence_level"),
            },
        )
