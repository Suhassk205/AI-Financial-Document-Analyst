"""Unit tests for operational endpoints.

`/health` and `/status` have no external dependencies, so they are pure unit
tests. `/ready` checks DB+Redis and therefore belongs to the integration suite
(added when those services are wired into CI).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.config import settings


@pytest.mark.unit
async def test_health_is_ok(client: AsyncClient) -> None:
    resp = await client.get(f"{settings.api_v1_prefix}/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.unit
async def test_status_reports_metadata(client: AsyncClient) -> None:
    resp = await client.get(f"{settings.api_v1_prefix}/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == settings.app_name
    assert "version" in body and "phase" in body


@pytest.mark.unit
async def test_request_id_header_is_echoed(client: AsyncClient) -> None:
    resp = await client.get(f"{settings.api_v1_prefix}/health")
    assert "X-Request-Id" in resp.headers
