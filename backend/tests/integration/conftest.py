"""Integration fixtures — require a live PostgreSQL (and create/drop schema).

These tests are marked `integration` and are intended to run in CI with the
docker-compose Postgres available. They build the schema with SQLAlchemy
`create_all` (and ensure pgcrypto for gen_random_uuid), exercise the real
async API and the sync Celery task against the same database, and tear down.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.orm import Session

import app.models  # noqa: F401 - register models on Base.metadata
from app.db.base import Base
from app.db.session import AsyncSessionLocal, SyncSessionLocal, get_db, sync_engine
from app.main import app

# Skip the whole integration suite gracefully if Postgres isn't reachable.
fitz = pytest.importorskip("fitz", reason="PyMuPDF not installed")


@pytest.fixture(scope="session", autouse=True)
def _schema() -> Generator[None, None, None]:
    with sync_engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        # Phase 2A: document_chunks now has a pgvector `vector(768)` column, so the
        # extension must exist before create_all builds the table.
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        Base.metadata.create_all(conn)
    yield
    with sync_engine.begin() as conn:
        Base.metadata.drop_all(conn)


@pytest.fixture(autouse=True)
def _clean_tables() -> Generator[None, None, None]:
    """Truncate between tests for isolation."""
    yield
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE conversation_messages, conversation_threads, risk_evolution, risk_factors, "
                "metric_comparisons, financial_metrics, document_chunks, report_sections, report_pages, "
                "reports, companies RESTART IDENTITY CASCADE"
            )
        )


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_async_engine() -> AsyncGenerator[None, None]:
    yield
    from app.db.session import engine
    await engine.dispose()


@pytest.fixture
def sync_session() -> Generator[Session, None, None]:
    with SyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def api_client(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[AsyncClient, None]:
    """Async client with get_db overridden and Celery enqueue stubbed."""

    async def _override_get_db():
        async with AsyncSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    class _Task:
        def delay(self, *args, **kwargs) -> None:  # no broker in tests
            return None

    # Stub the pipeline tasks: upload→process_report→detect_sections→generate_chunks
    # are chained via .delay(); tests invoke each task directly instead of via a broker.
    monkeypatch.setattr("app.tasks.ingestion.process_report", _Task())
    monkeypatch.setattr("app.tasks.ingestion.detect_sections", _Task())
    monkeypatch.setattr("app.tasks.ingestion.generate_chunks", _Task())
    # Phase 2A: the embeddings endpoint enqueues generate_embeddings_task.delay();
    # stub it in the endpoint's namespace so no broker is needed.
    monkeypatch.setattr("app.api.v1.endpoints.embeddings.generate_embeddings_task", _Task())
    # Phase 3A: the metrics endpoint enqueues extract_financial_metrics_task.delay().
    monkeypatch.setattr("app.api.v1.endpoints.metrics.extract_financial_metrics_task", _Task())
    # Phase 3B: the comparisons endpoint enqueues generate_metric_comparisons_task.delay().
    monkeypatch.setattr(
        "app.api.v1.endpoints.comparisons.generate_metric_comparisons_task", _Task()
    )
    # Phase 4: the risks endpoint enqueues extract_risks_task.delay().
    monkeypatch.setattr("app.api.v1.endpoints.risks.extract_risks_task", _Task())
    # Phase 5: the tone endpoint enqueues extract_management_tone_task.delay().
    monkeypatch.setattr("app.api.v1.endpoints.tone.extract_management_tone_task", _Task())

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    app.dependency_overrides.clear()


def _pdf_from_pages(page_lines: list[str]) -> bytes:
    doc = fitz.open()
    for body in page_lines:
        page = doc.new_page()
        # insert_text renders each "\n" as a new line, preserving headings on top.
        page.insert_text((72, 72), body)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def tiny_pdf_bytes() -> bytes:
    return _pdf_from_pages(["Revenue was $1,284 million.", "Risk factors discussion."])


@pytest.fixture
def tenk_pdf_bytes() -> bytes:
    return _pdf_from_pages(
        [
            "PART I\nItem 1. Business\nWe build robots.",
            "Item 1A. Risk Factors\nThe following risks could affect us.",
            "Item 7. Management's Discussion and Analysis\nRevenue rose.",
            "Item 8. Financial Statements\nConsolidated Balance Sheets.",
        ]
    )
