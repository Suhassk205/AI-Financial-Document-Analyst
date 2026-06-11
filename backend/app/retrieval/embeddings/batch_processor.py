"""Batch embedding processing (Phase 2A, task §6).

Turns a flat list of (chunk-id, text) into provider batches and yields one
outcome per batch, so the caller can persist + report progress incrementally
instead of buffering an entire 100–300 page report in memory.

Batching strategy (documented per task §6):
  * One Gemini `batchEmbedContents` request carries up to `batch_size` chunks
    (default 100 — the model's per-request item cap). This is what lets us avoid
    "one API request per chunk".
  * Report size scales the *number* of requests, not the strategy:
        - Small report  (≤ batch_size chunks)      → 1 request.
        - Medium report (a few × batch_size)        → a handful of requests.
        - Large report  (100–300 pages, 1000s chunks) → ⌈n / batch_size⌉ requests.
  * Failure isolation: a batch that fails *after the provider's internal
    retries* does not abort the run — its chunks are reported as failures and
    the next batch proceeds. This keeps one transient hiccup from losing a whole
    report's work.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.retrieval.embeddings.exceptions import EmbeddingError
from app.retrieval.embeddings.provider import Embedding, EmbeddingProvider

log = get_logger(__name__)


@dataclass(frozen=True)
class BatchItem:
    chunk_id: str
    text: str


@dataclass
class BatchOutcome:
    """Result of embedding a single batch."""

    results: list[tuple[str, Embedding]] = field(default_factory=list)  # (chunk_id, vector)
    failures: list[tuple[str, str]] = field(default_factory=list)       # (chunk_id, reason)
    api_calls: int = 0
    retries: int = 0


class BatchProcessor:
    """Splits work into provider batches and embeds them one batch at a time."""

    def __init__(self, provider: EmbeddingProvider, *, batch_size: int = 100) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        self.provider = provider
        self.batch_size = batch_size

    def plan_batch_count(self, item_count: int) -> int:
        """Number of provider requests a run of `item_count` chunks will make."""
        if item_count <= 0:
            return 0
        return -(-item_count // self.batch_size)  # ceil division

    def iter_batches(self, items: list[BatchItem]) -> Iterator[list[BatchItem]]:
        for start in range(0, len(items), self.batch_size):
            yield items[start : start + self.batch_size]

    def process(self, items: list[BatchItem]) -> Iterator[BatchOutcome]:
        """Yield one `BatchOutcome` per batch. Failures are isolated per batch."""
        for batch in self.iter_batches(items):
            outcome = BatchOutcome(api_calls=1)
            texts = [it.text for it in batch]
            retries_before = getattr(self.provider, "retry_count", 0)
            try:
                vectors = self.provider.embed_documents(texts)
            except EmbeddingError as exc:
                reason = f"{type(exc).__name__}: {exc}"
                log.error("embedding.batch_failed", size=len(batch), error=reason)
                outcome.failures = [(it.chunk_id, reason) for it in batch]
                outcome.retries = getattr(self.provider, "retry_count", 0) - retries_before
                yield outcome
                continue

            outcome.retries = getattr(self.provider, "retry_count", 0) - retries_before
            # Provider guarantees one vector per text (it validated the count).
            for it, vec in zip(batch, vectors, strict=True):
                outcome.results.append((it.chunk_id, vec))
            yield outcome
