"""Operational endpoints: /health (liveness), /ready (readiness), /status (info).

These are infrastructure endpoints only — NOT business endpoints. They let
orchestrators (Docker/K8s) and humans verify the service and its dependencies.

  * /health  — liveness: is the process up? No external dependencies checked.
               Used for container/K8s liveness probes; must be fast and never fail
               just because a downstream (DB/Redis) is degraded.
  * /ready   — readiness: can we serve traffic? Checks DB and Redis connectivity.
               Used for K8s readiness probes / load-balancer gating. Returns 503
               if a hard dependency is unavailable.
  * /status  — build/version/runtime metadata for humans and dashboards.
"""

from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, Response, status

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import ping as db_ping

router = APIRouter(tags=["operations"])
log = get_logger(__name__)


@router.get("/health", summary="Liveness probe")
async def health() -> dict:
    """Liveness: the process is running. Intentionally dependency-free."""
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe")
async def ready(response: Response) -> dict:
    """Readiness: verify hard dependencies (PostgreSQL, Redis) are reachable."""
    checks: dict[str, str] = {}

    # PostgreSQL
    try:
        await db_ping()
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 - report, don't crash the probe
        checks["database"] = "error"
        log.warning("readiness.database_failed", error=str(exc))

    # Redis
    try:
        client = aioredis.from_url(settings.redis_url)
        await client.ping()
        await client.aclose()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = "error"
        log.warning("readiness.redis_failed", error=str(exc))

    ready_ok = all(v == "ok" for v in checks.values())
    if not ready_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if ready_ok else "not_ready", "checks": checks}


@router.get("/status", summary="Service metadata")
async def service_status() -> dict:
    """Human/dashboard-facing build & runtime info (no secrets)."""
    return {
        "service": settings.app_name,
        "environment": settings.app_env.value,
        "version": "0.0.1",
        "phase": "0.5 — repository & infrastructure foundation",
        "debug": settings.debug,
    }
