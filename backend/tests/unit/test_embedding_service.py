"""Unit tests for the EmbeddingService orchestration (Phase 2A).

Uses an in-memory fake repository + fake provider — no DB, no network. Verifies
the workflow, idempotency, partial-failure handling, and metrics.
"""

from __future__ import annotations

import uuid

import pytest
from app.models.enums import EmbeddingStatus, ReportStatus
from app.retrieval.embeddings.embedding_service import EmbeddingService
from app.retrieval.embeddings.exceptions import TransientProviderError
from app.retrieval.embeddings.provider import EmbeddingProvider

DIM = 8


class FakeChunk:
    def __init__(self, idx: int, *, status=EmbeddingStatus.PENDING, embedding=None) -> None:
        self.id = uuid.uuid4()
        self.chunk_index = idx
        self.chunk_text = f"chunk text number {idx}"
        self.token_count = 10 + idx
        self.embedding = embedding
        self.embedding_status = status.value
        self.embedding_model = None
        self.embedding_generated_at = None


class FakeReport:
    def __init__(self) -> None:
        self.id = uuid.uuid4()
        self.status = ReportStatus.CHUNKED
        self.error_message = None
        self.processing_completed_at = None


class FakeRepo:
    def __init__(self, report: FakeReport, chunks: list[FakeChunk]) -> None:
        self.report = report
        self.chunks = chunks
        self.commits = 0

    def get_report(self, rid):
        return self.report if rid == self.report.id else None

    def get_chunks_for_embedding(self, report_id, *, include_completed=False):
        if include_completed:
            return list(self.chunks)
        return [c for c in self.chunks if c.embedding is None]

    def count_chunks(self, report_id):
        return len(self.chunks)

    def count_missing_embeddings(self, report_id):
        return sum(1 for c in self.chunks if c.embedding is None)

    def mark_embedding(self, report):
        report.status = ReportStatus.EMBEDDING

    def mark_embedded(self, report):
        report.status = ReportStatus.EMBEDDED

    def set_embedding_status(self, chunks, status):
        for c in chunks:
            c.embedding_status = status.value

    def apply_embedding(self, chunk, *, embedding, model):
        chunk.embedding = embedding
        chunk.embedding_model = model
        chunk.embedding_status = EmbeddingStatus.COMPLETED.value

    def commit(self):
        self.commits += 1


class FakeProvider(EmbeddingProvider):
    def __init__(self, *, dim=DIM, fail_on=None, bad_dim=False) -> None:
        self._dim = dim
        self.fail_on = fail_on
        self.bad_dim = bad_dim
        self.retry_count = 0

    @property
    def model_name(self):
        return "gemini-embedding-001"

    @property
    def dimension(self):
        return self._dim

    def embed_documents(self, texts):
        if self.fail_on and any(self.fail_on in t for t in texts):
            raise TransientProviderError("boom")
        width = self._dim - 1 if self.bad_dim else self._dim
        return [[0.1] * width for _ in texts]


@pytest.mark.unit
def test_happy_path_embeds_all_and_marks_report_embedded() -> None:
    report = FakeReport()
    chunks = [FakeChunk(i) for i in range(3)]
    repo = FakeRepo(report, chunks)
    service = EmbeddingService(repo, FakeProvider(), batch_size=100)

    metrics = service.generate_for_report(report.id)

    assert metrics.embedded == 3
    assert metrics.failed == 0
    assert metrics.api_calls == 1
    assert metrics.tokens == sum(c.token_count for c in chunks)
    assert metrics.estimated_cost_usd >= 0.0
    assert report.status == ReportStatus.EMBEDDED
    assert all(c.embedding is not None for c in chunks)
    assert all(c.embedding_status == EmbeddingStatus.COMPLETED.value for c in chunks)
    assert all(c.embedding_model == "gemini-embedding-001" for c in chunks)


@pytest.mark.unit
def test_idempotent_skips_already_completed() -> None:
    report = FakeReport()
    # All chunks already embedded.
    chunks = [
        FakeChunk(i, status=EmbeddingStatus.COMPLETED, embedding=[0.1] * DIM)
        for i in range(3)
    ]
    repo = FakeRepo(report, chunks)
    service = EmbeddingService(repo, FakeProvider(), batch_size=100)

    metrics = service.generate_for_report(report.id)

    assert metrics.embedded == 0
    assert metrics.total_chunks == 0  # working set is empty
    assert report.status == ReportStatus.EMBEDDED  # already complete → reconciled


@pytest.mark.unit
def test_force_reembeds_everything() -> None:
    report = FakeReport()
    chunks = [
        FakeChunk(i, status=EmbeddingStatus.COMPLETED, embedding=[0.9] * DIM)
        for i in range(2)
    ]
    repo = FakeRepo(report, chunks)
    service = EmbeddingService(repo, FakeProvider(), batch_size=100)

    metrics = service.generate_for_report(report.id, force=True)

    assert metrics.embedded == 2
    assert all(c.embedding == [0.1] * DIM for c in chunks)  # overwritten


@pytest.mark.unit
def test_partial_failure_marks_chunks_failed_and_not_embedded() -> None:
    report = FakeReport()
    chunks = [FakeChunk(i) for i in range(4)]
    repo = FakeRepo(report, chunks)
    # batch_size=2 → two batches; the batch with "number 2" fails.
    service = EmbeddingService(repo, FakeProvider(fail_on="number 2"), batch_size=2)

    metrics = service.generate_for_report(report.id)

    assert metrics.failed == 2
    assert metrics.embedded == 2
    assert report.status == ReportStatus.EMBEDDING  # NOT EMBEDDED (missing remain)
    failed = [c for c in chunks if c.embedding_status == EmbeddingStatus.FAILED.value]
    assert len(failed) == 2


@pytest.mark.unit
def test_invalid_dimension_is_caught_by_validator() -> None:
    report = FakeReport()
    chunks = [FakeChunk(i) for i in range(2)]
    repo = FakeRepo(report, chunks)
    service = EmbeddingService(repo, FakeProvider(bad_dim=True), batch_size=100)

    metrics = service.generate_for_report(report.id)

    assert metrics.embedded == 0
    assert metrics.failed == 2
    assert all(c.embedding is None for c in chunks)


@pytest.mark.unit
def test_no_chunks_raises() -> None:
    report = FakeReport()
    repo = FakeRepo(report, [])
    service = EmbeddingService(repo, FakeProvider(), batch_size=100)
    with pytest.raises(ValueError):
        service.generate_for_report(report.id)
