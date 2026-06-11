"""Embedding-layer exceptions (Phase 2A).

A small hierarchy so callers (service / task) can distinguish *transient* errors
(retry) from *permanent* ones (fail fast). The provider raises these; the
service/task decide policy.

These are deliberately separate from `app.core.exceptions` (HTTP-facing domain
errors) — embedding errors are internal infrastructure failures, not user errors.
"""

from __future__ import annotations


class EmbeddingError(Exception):
    """Base class for all embedding-layer failures."""


class EmbeddingConfigError(EmbeddingError):
    """Misconfiguration (missing API key, unset model/dimension). NOT retryable."""


class EmbeddingProviderError(EmbeddingError):
    """A call to the embedding provider failed. May be transient (see subclasses)."""

    #: Whether retrying the same call could plausibly succeed.
    retryable: bool = False


class RateLimitError(EmbeddingProviderError):
    """Provider returned a rate-limit / quota signal (HTTP 429). Retryable."""

    retryable = True

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class TransientProviderError(EmbeddingProviderError):
    """Transient server/network failure (HTTP 5xx, timeout, reset). Retryable."""

    retryable = True


class InvalidEmbeddingResponseError(EmbeddingProviderError):
    """The provider responded but the payload is unusable.

    Examples: wrong number of vectors, wrong dimension, empty/all-zero vector,
    non-finite values. NOT retryable — the same input would reproduce it.
    """

    retryable = False
