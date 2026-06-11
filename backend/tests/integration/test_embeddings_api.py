"""Integration tests for Phase 2A: chunk → embedding → pgvector + embedding APIs.

A fake provider is used end-to-end so CI needs no Gemini key/network, but the
real EmbeddingService, repository, pgvector column, and FastAPI endpoints are
exercised against a live PostgreSQL.
"""

from __future__ import annotations

import uuid

import pytest
from app.core.config import settings
from app.models.document_chunk import DocumentChunk
from app.models.enums import EmbeddingStatus, ReportStatus
from app.models.report import Report
from app.repositories.report_repository import SyncReportRepository
from app.retrieval.embeddings import EmbeddingService
from app.retrieval.embeddings.exceptions import TransientProviderError
from app.retrieval.embeddings.provider import EmbeddingProvider
from app.tasks.ingestion import detect_sections, generate_chunks, process_report
from httpx import AsyncClient
from sqlalchemy.orm import Session

PREFIX = settings.api_v1_prefix
DIM = settings.embedding_dim


class FakeProvider(EmbeddingProvider):
    """Deterministic in-test provider producing correctly-sized vectors."""

    def __init__(self, *, fail_all: bool = False) -> None:
        self.fail_all = fail_all
        self.retry_count = 0

    @property
    def model_name(self) -> str:
        return settings.gemini_embedding_model

    @property
    def dimension(self) -> int:
        return DIM

    def embed_documents(self, texts):
        if self.fail_all:
            raise TransientProviderError("boom")
        return [[0.01] * DIM for _ in texts]


async def _upload(client: AsyncClient, data: bytes) -> str:
    resp = await client.post(
        f"{PREFIX}/reports/upload",
        files={"file": ("f.pdf", data, "application/pdf")},
        data={"report_type": "10-K", "year": "2025", "ticker": "ACME"},
    )
    assert resp.status_code == 202, resp.text
    return resp.json()["report_id"]


def _run_embeddings(report_id: str, *, fail_all: bool = False) -> None:
    """Run the real EmbeddingService with a fake provider against the DB."""
    from app.db.session import SyncSessionLocal

    with SyncSessionLocal() as session:
        repo = SyncReportRepository(session)
        service = EmbeddingService(repo, FakeProvider(fail_all=fail_all), batch_size=100)
        service.generate_for_report(uuid.UUID(report_id))


@pytest.mark.integration
async def test_chunk_to_embedding_to_db_and_apis(
    api_client: AsyncClient, tenk_pdf_bytes: bytes, sync_session: Session
) -> None:
    report_id = await _upload(api_client, tenk_pdf_bytes)
    assert process_report(report_id)["status"] == "PROCESSED"
    assert detect_sections(report_id)["status"] == "SECTIONED"
    chunked = generate_chunks(report_id)
    assert chunked["status"] == "CHUNKED"
    total = chunked["chunks"]

    # Before embedding: stats show none embedded, all missing.
    stats = (await api_client.get(f"{PREFIX}/reports/{report_id}/embeddings/stats")).json()
    assert stats["total_chunks"] == total
    assert stats["embedded_chunks"] == 0
    assert stats["missing_chunks"] == total
    assert stats["dimension"] == DIM
    assert stats["model"] == settings.gemini_embedding_model
    assert stats["fully_embedded"] is False

    # Generate embeddings (real service, fake provider).
    _run_embeddings(report_id)

    # After embedding: every chunk has a vector.
    stats = (await api_client.get(f"{PREFIX}/reports/{report_id}/embeddings/stats")).json()
    assert stats["total_chunks"] == total
    assert stats["embedded_chunks"] == total
    assert stats["missing_chunks"] == 0
    assert stats["fully_embedded"] is True

    status = (await api_client.get(f"{PREFIX}/reports/{report_id}/embeddings/status")).json()
    assert status["completed"] == total
    assert status["pending"] == 0 and status["failed"] == 0

    detail = (await api_client.get(f"{PREFIX}/reports/{report_id}")).json()
    assert detail["status"] == ReportStatus.EMBEDDED.value

    # DB: the vector column round-trips at the right width and is marked COMPLETED.
    rows = (
        sync_session.query(DocumentChunk)
        .filter(DocumentChunk.report_id == report_id)
        .all()
    )
    assert len(rows) == total
    for c in rows:
        assert c.embedding is not None
        assert len(c.embedding) == DIM
        assert c.embedding_status == EmbeddingStatus.COMPLETED.value
        assert c.embedding_model == settings.gemini_embedding_model


@pytest.mark.integration
async def test_generate_endpoint_enqueues(
    api_client: AsyncClient, tenk_pdf_bytes: bytes
) -> None:
    report_id = await _upload(api_client, tenk_pdf_bytes)
    process_report(report_id)
    detect_sections(report_id)
    generate_chunks(report_id)

    resp = await api_client.post(f"{PREFIX}/reports/{report_id}/embeddings/generate")
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["task_enqueued"] is True
    assert body["force"] is False


@pytest.mark.integration
async def test_generate_with_no_chunks_is_noop(api_client: AsyncClient) -> None:
    # A report with zero chunks → endpoint reports nothing to do (no task).
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        report = Report(
            report_type="10-K", year=2025, original_filename="x.pdf",
            storage_path="reports/2026/06/none.pdf", status=ReportStatus.CHUNKED,
        )
        session.add(report)
        await session.commit()
        rid = str(report.id)

    resp = await api_client.post(f"{PREFIX}/reports/{rid}/embeddings/generate")
    assert resp.status_code == 202
    assert resp.json()["task_enqueued"] is False


@pytest.mark.integration
async def test_embedding_endpoints_404_for_unknown_report(api_client: AsyncClient) -> None:
    unknown = "00000000-0000-0000-0000-000000000000"
    for path in ("status", "stats"):
        resp = await api_client.get(f"{PREFIX}/reports/{unknown}/embeddings/{path}")
        assert resp.status_code == 404
    resp = await api_client.post(f"{PREFIX}/reports/{unknown}/embeddings/generate")
    assert resp.status_code == 404


@pytest.mark.integration
async def test_partial_failure_leaves_report_not_embedded(
    api_client: AsyncClient, tenk_pdf_bytes: bytes, sync_session: Session
) -> None:
    report_id = await _upload(api_client, tenk_pdf_bytes)
    process_report(report_id)
    detect_sections(report_id)
    generate_chunks(report_id)

    # Fail every batch: no chunk gets a vector.
    _run_embeddings(report_id, fail_all=True)

    stats = (await api_client.get(f"{PREFIX}/reports/{report_id}/embeddings/stats")).json()
    assert stats["embedded_chunks"] == 0
    assert stats["fully_embedded"] is False
    detail = (await api_client.get(f"{PREFIX}/reports/{report_id}")).json()
    assert detail["status"] != ReportStatus.EMBEDDED.value


@pytest.mark.integration
async def test_embedding_run_is_idempotent(
    api_client: AsyncClient, tenk_pdf_bytes: bytes, sync_session: Session
) -> None:
    report_id = await _upload(api_client, tenk_pdf_bytes)
    process_report(report_id)
    detect_sections(report_id)
    total = generate_chunks(report_id)["chunks"]

    _run_embeddings(report_id)
    _run_embeddings(report_id)  # second run should be a no-op (all COMPLETED)

    rows = (
        sync_session.query(DocumentChunk)
        .filter(DocumentChunk.report_id == report_id)
        .all()
    )
    assert len(rows) == total
    assert all(c.embedding is not None for c in rows)
