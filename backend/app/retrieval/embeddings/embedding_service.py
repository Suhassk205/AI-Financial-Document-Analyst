"""Embedding service (Phase 2A, task §5).

Orchestrates the per-report embedding run on the Celery worker (synchronous,
like the Phase 1 ingestion stages). It does NOT talk HTTP and does NOT do
retrieval — it only converts chunks into stored vectors.

Workflow (task §5):
    load chunks needing embeddings
        → generate embedding (batched, via BatchProcessor + provider)
        → validate embedding (EmbeddingValidator)
        → store embedding (pgvector column) + mark chunk COMPLETED
        → track progress / metrics
    → mark report EMBEDDED iff every chunk now has a valid embedding.

Idempotency / no-duplicate-work (task §13): by default only chunks WITHOUT a
COMPLETED embedding are processed, so re-running the task (or recovering from a
partial failure) never re-embeds, re-bills, or overwrites good vectors. `force`
re-embeds everything (e.g. after a model change).
"""

from __future__ import annotations

import time
import uuid

from app.core.config import settings
from app.core.logging import get_logger
from app.models.document_chunk import DocumentChunk
from app.models.enums import EmbeddingStatus
from app.repositories.report_repository import SyncReportRepository
from app.retrieval.embeddings.batch_processor import BatchItem, BatchProcessor
from app.retrieval.embeddings.embedding_validator import EmbeddingValidator
from app.retrieval.embeddings.metrics import EmbeddingMetrics
from app.retrieval.embeddings.provider import EmbeddingProvider

log = get_logger(__name__)


class EmbeddingService:
    def __init__(
        self,
        repo: SyncReportRepository,
        provider: EmbeddingProvider,
        *,
        batch_size: int | None = None,
        validator: EmbeddingValidator | None = None,
    ) -> None:
        self.repo = repo
        self.provider = provider
        self.batch_processor = BatchProcessor(
            provider, batch_size=batch_size or settings.embedding_batch_size
        )
        self.validator = validator or EmbeddingValidator(dimension=provider.dimension)

    def generate_for_report(
        self, report_id: uuid.UUID, *, force: bool = False
    ) -> EmbeddingMetrics:
        """Embed every chunk of a report that still needs it. Returns run metrics."""
        metrics = EmbeddingMetrics(report_id=str(report_id))
        started = time.monotonic()

        report = self.repo.get_report(report_id)
        if report is None:
            raise ValueError(f"report {report_id} not found")

        chunks = self.repo.get_chunks_for_embedding(report_id, include_completed=force)
        total_in_report = self.repo.count_chunks(report_id)
        if total_in_report == 0:
            raise ValueError("no chunks to embed (report not chunked?)")

        metrics.total_chunks = len(chunks)
        self.repo.mark_embedding(report)

        if not chunks:
            # Nothing to do — every chunk is already embedded. Still reconcile status.
            self._finalize(report_id, metrics, started)
            return metrics

        # Mark the working set PROCESSING for operational visibility.
        self.repo.set_embedding_status(chunks, EmbeddingStatus.PROCESSING)

        by_id: dict[str, DocumentChunk] = {str(c.id): c for c in chunks}
        items = [BatchItem(chunk_id=str(c.id), text=c.chunk_text) for c in chunks]

        planned = self.batch_processor.plan_batch_count(len(items))
        log.info(
            "embedding.run_start",
            report_id=str(report_id),
            chunks=len(items),
            planned_batches=planned,
            model=self.provider.model_name,
            dimension=self.provider.dimension,
        )

        done = 0
        for outcome in self.batch_processor.process(items):
            metrics.api_calls += outcome.api_calls
            metrics.retries += outcome.retries

            for chunk_id, vector in outcome.results:
                chunk = by_id[chunk_id]
                vres = self.validator.validate(
                    embedding=vector,
                    current_status=None,  # provider just produced it
                    chunk_id=chunk_id,
                )
                if vres.is_valid:
                    self.repo.apply_embedding(
                        chunk, embedding=vector, model=self.provider.model_name
                    )
                    metrics.embedded += 1
                    metrics.tokens += chunk.token_count or 0
                else:
                    self.repo.set_embedding_status([chunk], EmbeddingStatus.FAILED)
                    metrics.failed += 1

            for chunk_id, reason in outcome.failures:
                self.repo.set_embedding_status([by_id[chunk_id]], EmbeddingStatus.FAILED)
                metrics.failed += 1
                log.warning("embedding.chunk_failed", chunk_id=chunk_id, reason=reason)

            self.repo.commit()  # persist this batch before moving on
            done += len(outcome.results) + len(outcome.failures)
            log.info(
                "embedding.progress",
                report_id=str(report_id),
                processed=done,
                total=len(items),
            )

        self._finalize(report_id, metrics, started)
        return metrics

    def _finalize(
        self, report_id: uuid.UUID, metrics: EmbeddingMetrics, started: float
    ) -> None:
        metrics.duration_seconds = round(time.monotonic() - started, 3)
        metrics.estimate_cost(settings.embedding_price_per_1m_tokens)

        missing = self.repo.count_missing_embeddings(report_id)
        report = self.repo.get_report(report_id)
        if report is not None and missing == 0:
            self.repo.mark_embedded(report)

        log.info(
            "embedding.run_complete",
            **metrics.as_dict(),
            missing_after=missing,
        )
