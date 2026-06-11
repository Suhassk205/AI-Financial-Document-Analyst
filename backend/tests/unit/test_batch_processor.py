"""Unit tests for the embedding batch processor (Phase 2A)."""

from __future__ import annotations

import pytest
from app.retrieval.embeddings.batch_processor import BatchItem, BatchProcessor
from app.retrieval.embeddings.exceptions import TransientProviderError
from app.retrieval.embeddings.provider import EmbeddingProvider

DIM = 4


class FakeProvider(EmbeddingProvider):
    """Deterministic provider; raises on any text containing `fail_on`."""

    def __init__(self, *, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.calls = 0
        self.retry_count = 0

    @property
    def model_name(self) -> str:
        return "fake-model"

    @property
    def dimension(self) -> int:
        return DIM

    def embed_documents(self, texts):
        self.calls += 1
        if self.fail_on and any(self.fail_on in t for t in texts):
            raise TransientProviderError("boom")
        return [[float(len(t))] * DIM for t in texts]


def _items(n: int) -> list[BatchItem]:
    return [BatchItem(chunk_id=str(i), text=f"chunk-{i}") for i in range(n)]


@pytest.mark.unit
@pytest.mark.parametrize(
    "count,size,expected",
    [(0, 100, 0), (1, 100, 1), (100, 100, 1), (101, 100, 2), (250, 100, 3), (5, 2, 3)],
)
def test_plan_batch_count(count, size, expected) -> None:
    bp = BatchProcessor(FakeProvider(), batch_size=size)
    assert bp.plan_batch_count(count) == expected


@pytest.mark.unit
def test_small_report_single_request() -> None:
    bp = BatchProcessor(FakeProvider(), batch_size=100)
    outcomes = list(bp.process(_items(10)))
    assert len(outcomes) == 1
    assert outcomes[0].api_calls == 1
    assert len(outcomes[0].results) == 10
    assert not outcomes[0].failures


@pytest.mark.unit
def test_large_report_multiple_batches() -> None:
    provider = FakeProvider()
    bp = BatchProcessor(provider, batch_size=100)
    outcomes = list(bp.process(_items(250)))
    assert len(outcomes) == 3                      # ceil(250/100)
    assert provider.calls == 3                      # not one-per-chunk
    total_results = sum(len(o.results) for o in outcomes)
    assert total_results == 250


@pytest.mark.unit
def test_batch_failure_is_isolated() -> None:
    # Only the batch containing chunk-3 fails; the other batch still succeeds.
    provider = FakeProvider(fail_on="chunk-3")
    bp = BatchProcessor(provider, batch_size=2)
    outcomes = list(bp.process(_items(6)))
    failed = [o for o in outcomes if o.failures]
    ok = [o for o in outcomes if o.results]
    assert failed, "expected at least one failed batch"
    assert ok, "other batches should still succeed"
    # every item is accounted for exactly once
    total = sum(len(o.results) + len(o.failures) for o in outcomes)
    assert total == 6


@pytest.mark.unit
def test_invalid_batch_size_rejected() -> None:
    with pytest.raises(ValueError):
        BatchProcessor(FakeProvider(), batch_size=0)
