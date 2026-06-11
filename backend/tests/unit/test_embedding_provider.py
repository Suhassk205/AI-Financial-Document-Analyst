"""Unit tests for the Gemini embedding provider (Phase 2A).

No network / SDK: tests subclass the provider and override `_embed_once`, or call
the pure helpers (`_classify`, `_normalize_vector`, `_validate`) directly.
"""

from __future__ import annotations

import math

import pytest
from app.retrieval.embeddings.exceptions import (
    EmbeddingConfigError,
    EmbeddingProviderError,
    InvalidEmbeddingResponseError,
    RateLimitError,
    TransientProviderError,
)
from app.retrieval.embeddings.gemini_provider import GeminiEmbeddingProvider

DIM = 8


def make_provider(responses=None, *, normalize=True, max_retries=3, errors=None):
    """Build a provider whose `_embed_once` is scripted.

    `errors`: list of exceptions to raise on successive calls before succeeding.
    `responses`: the vectors to return once errors are exhausted.
    """
    calls = {"n": 0}
    err_iter = list(errors or [])

    class _P(GeminiEmbeddingProvider):
        def _embed_once(self, texts):
            calls["n"] += 1
            if err_iter:
                raise err_iter.pop(0)
            if responses is not None:
                return [list(r) for r in responses]
            # default: un-normalized vector per text
            return [[0.3] * DIM for _ in texts]

    p = _P(
        api_key="x",
        model="gemini-embedding-001",
        dimension=DIM,
        normalize=normalize,
        max_retries=max_retries,
        base_delay=0.0,
        max_delay=0.0,
        client=object(),
        sleep=lambda _delay: None,
    )
    p._calls = calls  # type: ignore[attr-defined]
    return p


@pytest.mark.unit
def test_empty_input_makes_no_call() -> None:
    p = make_provider()
    assert p.embed_documents([]) == []
    assert p._calls["n"] == 0  # type: ignore[attr-defined]


@pytest.mark.unit
def test_returns_one_vector_per_text_normalized() -> None:
    p = make_provider(normalize=True)
    out = p.embed_documents(["a", "b", "c"])
    assert len(out) == 3
    for v in out:
        assert len(v) == DIM
        assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, rel_tol=1e-9)


@pytest.mark.unit
def test_no_normalization_when_disabled() -> None:
    p = make_provider(normalize=False)
    out = p.embed_documents(["a"])
    norm = math.sqrt(sum(x * x for x in out[0]))
    assert not math.isclose(norm, 1.0)


@pytest.mark.unit
def test_count_mismatch_is_invalid() -> None:
    p = make_provider(responses=[[0.1] * DIM])  # 1 vector for 2 inputs
    with pytest.raises(InvalidEmbeddingResponseError):
        p.embed_documents(["a", "b"])


@pytest.mark.unit
def test_wrong_dimension_is_invalid() -> None:
    p = make_provider(responses=[[0.1] * (DIM + 1)])
    with pytest.raises(InvalidEmbeddingResponseError):
        p.embed_documents(["a"])


@pytest.mark.unit
def test_zero_norm_vector_is_invalid_when_normalizing() -> None:
    p = make_provider(responses=[[0.0] * DIM], normalize=True)
    with pytest.raises(InvalidEmbeddingResponseError):
        p.embed_documents(["a"])


@pytest.mark.unit
def test_retries_on_rate_limit_then_succeeds() -> None:
    p = make_provider(errors=[RateLimitError("429"), RateLimitError("429")], max_retries=3)
    out = p.embed_documents(["a"])
    assert len(out) == 1
    assert p.retry_count == 2
    assert p._calls["n"] == 3  # type: ignore[attr-defined]  # 2 failures + 1 success


@pytest.mark.unit
def test_retries_exhausted_reraises() -> None:
    p = make_provider(errors=[RateLimitError("429")] * 5, max_retries=2)
    with pytest.raises(RateLimitError):
        p.embed_documents(["a"])
    assert p.retry_count == 2  # capped at max_retries


@pytest.mark.unit
def test_non_retryable_error_not_retried() -> None:
    p = make_provider(errors=[InvalidEmbeddingResponseError("bad")], max_retries=3)
    with pytest.raises(InvalidEmbeddingResponseError):
        p.embed_documents(["a"])
    assert p.retry_count == 0


@pytest.mark.unit
def test_missing_model_raises_config_error() -> None:
    with pytest.raises(EmbeddingConfigError):
        GeminiEmbeddingProvider(api_key="x", model="", dimension=DIM)


@pytest.mark.unit
@pytest.mark.parametrize(
    "exc,expected",
    [
        (Exception("rate limit exceeded"), RateLimitError),
        (Exception("RESOURCE_EXHAUSTED"), RateLimitError),
        (Exception("service unavailable"), TransientProviderError),
        (Exception("connection reset"), TransientProviderError),
        (Exception("invalid argument"), EmbeddingProviderError),
    ],
)
def test_classify_maps_errors(exc, expected) -> None:
    assert isinstance(GeminiEmbeddingProvider._classify(exc), expected)


@pytest.mark.unit
def test_classify_by_status_code() -> None:
    class CodedError(Exception):
        def __init__(self, code: int) -> None:
            super().__init__(f"http {code}")
            self.code = code

    assert isinstance(GeminiEmbeddingProvider._classify(CodedError(429)), RateLimitError)
    assert isinstance(GeminiEmbeddingProvider._classify(CodedError(503)), TransientProviderError)
