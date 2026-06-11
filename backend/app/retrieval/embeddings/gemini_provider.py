"""Gemini embedding provider (Phase 2A).

Concrete `EmbeddingProvider` backed by Google's `gemini-embedding-001` model via
the `google-genai` SDK. Responsibilities (task §4): generate embeddings, handle
retries, handle rate limits, validate responses.

Key model facts — VERIFIED by calling the live model before locking them in:
  * Native output dimension is 3072 (L2-normalized).
  * `output_dimensionality` truncates via Matryoshka representation learning
    (MRL) to 768 / 1536 / 3072.
  * Truncated outputs (< 3072) come back NOT normalized, so we re-normalize to
    unit length here (required for correct cosine / dot-product similarity in
    Phase 2B). See ADR-013.

The SDK is imported lazily so this module (and the rest of the app) imports
cleanly even where `google-genai` isn't installed; unit tests subclass and
override `_embed_once` to avoid any network/SDK dependency.

Configuration comes exclusively from `Settings` / environment — the API key is
never hardcoded.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable

from app.core.config import settings as app_settings
from app.core.logging import get_logger
from app.retrieval.embeddings.exceptions import (
    EmbeddingConfigError,
    EmbeddingProviderError,
    InvalidEmbeddingResponseError,
    RateLimitError,
    TransientProviderError,
)
from app.retrieval.embeddings.provider import Embedding, EmbeddingProvider

log = get_logger(__name__)


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Generate embeddings with Gemini, with retry/rate-limit/validation built in."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dimension: int,
        task_type: str = "RETRIEVAL_DOCUMENT",
        normalize: bool = True,
        max_retries: int = 5,
        base_delay: float = 2.0,
        max_delay: float = 60.0,
        timeout: float = 60.0,
        client: object | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not model:
            raise EmbeddingConfigError("embedding model is not configured")
        if dimension <= 0:
            raise EmbeddingConfigError(f"invalid embedding dimension: {dimension}")
        self._api_key = api_key
        self._model = model
        self._dimension = dimension
        self._task_type = task_type
        self._normalize = normalize
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._timeout = timeout
        self._client = client
        self._sleep = sleep
        #: total provider retries across this instance's lifetime (observability).
        self.retry_count = 0

    # ---- factory -------------------------------------------------------------

    @classmethod
    def from_settings(cls, *, client: object | None = None) -> GeminiEmbeddingProvider:
        """Build a provider from application settings (the production path)."""
        return cls(
            api_key=app_settings.gemini_api_key,
            model=app_settings.gemini_embedding_model,
            dimension=app_settings.embedding_dim,
            task_type=app_settings.embedding_task_type,
            normalize=app_settings.embedding_normalize,
            max_retries=app_settings.embedding_max_retries,
            base_delay=app_settings.embedding_retry_base_delay,
            max_delay=app_settings.embedding_retry_max_delay,
            timeout=app_settings.embedding_request_timeout,
            client=client,
        )

    # ---- interface -----------------------------------------------------------

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_documents(self, texts: list[str]) -> list[Embedding]:
        """Embed a batch of chunk texts (one API call, with retries)."""
        if not texts:
            return []
        vectors = self._with_retries(lambda: self._embed_once(texts))
        self._validate(texts, vectors)
        if self._normalize:
            vectors = [self._normalize_vector(v) for v in vectors]
        return vectors

    # ---- network call (overridden in tests) ---------------------------------

    def _get_client(self) -> object:
        if self._client is None:
            if not self._api_key:
                raise EmbeddingConfigError("GEMINI_API_KEY is not set")
            try:
                from google import genai  # lazy import — optional dependency
            except ImportError as exc:  # pragma: no cover - import guard
                raise EmbeddingConfigError(
                    "google-genai is not installed; add it to requirements"
                ) from exc
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def _embed_once(self, texts: list[str]) -> list[Embedding]:
        """Single un-retried call to the provider. Returns raw vectors."""
        from google.genai import types  # lazy import

        client = self._get_client()
        try:
            resp = client.models.embed_content(  # type: ignore[attr-defined]
                model=self._model,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type=self._task_type,
                    output_dimensionality=self._dimension,
                ),
            )
        except Exception as exc:  # noqa: BLE001 - classify into our hierarchy
            raise self._classify(exc) from exc
        return [list(e.values) for e in resp.embeddings]

    # ---- retry / backoff -----------------------------------------------------

    def _with_retries(self, call: Callable[[], list[Embedding]]) -> list[Embedding]:
        attempt = 0
        while True:
            try:
                return call()
            except EmbeddingProviderError as exc:
                if not getattr(exc, "retryable", False) or attempt >= self._max_retries:
                    raise
                delay = min(self._base_delay * (2 ** attempt), self._max_delay)
                if isinstance(exc, RateLimitError) and exc.retry_after:
                    delay = max(delay, exc.retry_after)
                attempt += 1
                self.retry_count += 1
                log.warning(
                    "embedding.retry",
                    attempt=attempt,
                    max_retries=self._max_retries,
                    delay=round(delay, 2),
                    error=type(exc).__name__,
                )
                self._sleep(delay)

    @staticmethod
    def _classify(exc: Exception) -> EmbeddingProviderError:
        """Map an SDK/transport exception to our retryable/permanent hierarchy."""
        if isinstance(exc, EmbeddingProviderError):
            return exc
        code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        msg = str(exc)
        lowered = msg.lower()
        if code == 429 or "rate limit" in lowered or "quota" in lowered or "resource_exhausted" in lowered:
            return RateLimitError(msg)
        if (isinstance(code, int) and code >= 500) or "timeout" in lowered or "timed out" in lowered \
                or "connection" in lowered or "unavailable" in lowered:
            return TransientProviderError(msg)
        # Unknown 4xx / other → treat as permanent provider error.
        return EmbeddingProviderError(msg)

    # ---- validation / normalization -----------------------------------------

    def _validate(self, texts: list[str], vectors: list[Embedding]) -> None:
        if len(vectors) != len(texts):
            raise InvalidEmbeddingResponseError(
                f"provider returned {len(vectors)} vectors for {len(texts)} inputs"
            )
        for i, v in enumerate(vectors):
            if not v:
                raise InvalidEmbeddingResponseError(f"empty vector at index {i}")
            if len(v) != self._dimension:
                raise InvalidEmbeddingResponseError(
                    f"vector {i} has dim {len(v)}, expected {self._dimension}"
                )
            if any(not math.isfinite(x) for x in v):
                raise InvalidEmbeddingResponseError(f"vector {i} contains non-finite values")

    @staticmethod
    def _normalize_vector(v: Embedding) -> Embedding:
        norm = math.sqrt(sum(x * x for x in v))
        if norm == 0.0:
            # All-zero is invalid for cosine similarity; surface rather than divide.
            raise InvalidEmbeddingResponseError("zero-norm vector cannot be normalized")
        return [x / norm for x in v]
