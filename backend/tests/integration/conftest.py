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
        Base.metadata.create_all(conn)
    yield
    with sync_engine.begin() as conn:
        Base.metadata.drop_all(conn)


@pytest.fixture(autouse=True)
def _clean_tables() -> Generator[None, None, None]:
    """Truncate between tests for isolation."""
    yield
    with sync_engine.begin() as conn:
        conn.execute(text("TRUNCATE report_pages, reports, companies RESTART IDENTITY CASCADE"))


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
        def delay(self, report_id: str) -> None:  # no broker in tests
            return None

    monkeypatch.setattr("app.tasks.ingestion.process_report", _Task())

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    app.dependency_overrides.clear()


@pytest.fixture
def tiny_pdf_bytes() -> bytes:
    doc = fitz.open()
    for txt in ["Revenue was $1,284 million.", "Risk factors discussion."]:
        page = doc.new_page()
        page.insert_text((72, 72), txt)
    data = doc.tobytes()
    doc.close()
    return data
