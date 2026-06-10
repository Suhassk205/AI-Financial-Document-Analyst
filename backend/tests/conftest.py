"""Shared pytest fixtures.

Provides an async HTTP client bound to the FastAPI app for endpoint tests.
Integration fixtures that require live Postgres/Redis are added in later phases
and gated behind the `integration` marker.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async client that runs the app's lifespan (logging, etc.)."""
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
