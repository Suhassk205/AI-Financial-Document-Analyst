"""Embedding observability metrics (Phase 2A, task §11).

A plain accumulator the service fills during a run and logs/returns at the end.
Tracks the signals task §11 calls for: generation time, chunks processed,
failures, retry counts, API usage (calls + tokens), and a cost estimate.

This is intentionally in-process and lightweight — a metrics *backend*
(Prometheus/OTel) is a Phase 11 concern. The point here is operational
visibility for the embedding pipeline today.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class EmbeddingMetrics:
    report_id: str
    total_chunks: int = 0          # chunks considered this run
    embedded: int = 0             # newly embedded successfully
    skipped: int = 0              # already COMPLETED (idempotent skip)
    failed: int = 0               # validation/provider failures
    api_calls: int = 0            # provider batch requests issued
    retries: int = 0             # provider retries across the run
    tokens: int = 0              # approx input tokens embedded (for cost)
    duration_seconds: float = 0.0
    estimated_cost_usd: float = 0.0

    @property
    def chunks_per_second(self) -> float:
        if self.duration_seconds <= 0:
            return 0.0
        return round(self.embedded / self.duration_seconds, 2)

    def estimate_cost(self, price_per_1m_tokens: float) -> float:
        self.estimated_cost_usd = round(self.tokens / 1_000_000 * price_per_1m_tokens, 6)
        return self.estimated_cost_usd

    def as_dict(self) -> dict:
        d = asdict(self)
        d["chunks_per_second"] = self.chunks_per_second
        return d
