"""Unit tests for operational and demo mode endpoints.

`/health` and `/status` have no external dependencies, so they are pure unit
tests. `/ready` checks DB+Redis and therefore belongs to the integration suite
(added when those services are wired into CI).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.config import settings, Environment


@pytest.mark.unit
async def test_health_is_ok(client: AsyncClient) -> None:
    resp = await client.get(f"{settings.api_v1_prefix}/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "demo_mode": settings.demo_mode}


@pytest.mark.unit
async def test_status_reports_metadata(client: AsyncClient) -> None:
    resp = await client.get(f"{settings.api_v1_prefix}/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == settings.app_name
    assert "version" in body and "phase" in body
    assert body["demo_mode"] is settings.demo_mode


@pytest.mark.unit
async def test_request_id_header_is_echoed(client: AsyncClient) -> None:
    resp = await client.get(f"{settings.api_v1_prefix}/health")
    assert "X-Request-Id" in resp.headers


@pytest.mark.unit
async def test_demo_mode_status_endpoints(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "demo_mode", True)
    
    resp_health = await client.get(f"{settings.api_v1_prefix}/health")
    assert resp_health.status_code == 200
    assert resp_health.json()["demo_mode"] is True

    resp_status = await client.get(f"{settings.api_v1_prefix}/status")
    assert resp_status.status_code == 200
    assert resp_status.json()["demo_mode"] is True


@pytest.mark.unit
async def test_demo_mode_bypasses_auth(client: AsyncClient, monkeypatch) -> None:
    # Set to production environment and DEMO_MODE=True
    monkeypatch.setattr(settings, "app_env", Environment.PRODUCTION)
    monkeypatch.setattr(settings, "demo_mode", True)

    # Calling a protected endpoint without an Authorization header should succeed and return the demo user
    resp = await client.get(f"{settings.api_v1_prefix}/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "demo@example.com"
    assert body["role"] == "ADMIN"
