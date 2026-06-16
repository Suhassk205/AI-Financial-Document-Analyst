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

import os
import uuid
import redis.asyncio as aioredis
from fastapi import APIRouter, Response, status
from fastapi.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import ping as db_ping
from app.tasks.celery_app import celery_app
from app.retrieval.embeddings.gemini_provider import GeminiEmbeddingProvider

router = APIRouter(tags=["operations"])
log = get_logger(__name__)


async def perform_full_checks() -> dict[str, str]:
    """Execute connectivity and health checks across all downstream dependencies."""
    checks: dict[str, str] = {}

    # 1. PostgreSQL DB Pool Ping
    try:
        await db_ping()
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = "error"
        log.warning("healthcheck.database_failed", error=str(exc))

    # 2. Redis Connection Ping
    try:
        client = aioredis.from_url(settings.redis_url)
        await client.ping()
        await client.aclose()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = "error"
        log.warning("healthcheck.redis_failed", error=str(exc))

    # 3. Celery Workers Active Ping
    try:
        def check_celery():
            inspect = celery_app.control.inspect(timeout=1.0)
            res = inspect.ping()
            return "ok" if res else "no_workers"

        checks["celery"] = await run_in_threadpool(check_celery)
    except Exception as exc:  # noqa: BLE001
        checks["celery"] = "error"
        log.warning("healthcheck.celery_failed", error=str(exc))

    # 4. Gemini SDK API Connectivity check
    try:
        provider = GeminiEmbeddingProvider.from_settings()
        if provider.enabled:
            # Quick dummy check to test Gemini connection
            await run_in_threadpool(provider.embed_query, "healthcheck")
            checks["gemini"] = "ok"
        else:
            checks["gemini"] = "disabled"
    except Exception as exc:  # noqa: BLE001
        checks["gemini"] = "error"
        log.warning("healthcheck.gemini_failed", error=str(exc))

    # 5. Local/Object Storage Read/Write Validation
    try:
        path = settings.storage_local_path
        os.makedirs(path, exist_ok=True)
        temp_file = os.path.join(path, f".healthcheck_{uuid.uuid4()}")
        with open(temp_file, "w") as f:
            f.write("ok")
        os.remove(temp_file)
        checks["storage"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["storage"] = "error"
        log.warning("healthcheck.storage_failed", error=str(exc))

    return checks


@router.get("/health", summary="Liveness probe")
async def health() -> dict:
    """Liveness: the process is running. Intentionally dependency-free."""
    return {"status": "ok", "demo_mode": settings.demo_mode}


@router.get("/ready", summary="Readiness probe")
async def ready(response: Response) -> dict:
    """Readiness: verify dependencies are reachable. Sets 503 if DB/Redis are down."""
    checks = await perform_full_checks()
    ready_ok = checks.get("database") == "ok" and checks.get("redis") == "ok"
    if not ready_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if ready_ok else "not_ready", "checks": checks}


@router.get("/status", summary="Service metadata")
async def service_status() -> dict:
    """Human/dashboard-facing build & runtime info with connectivity details."""
    checks = await perform_full_checks()
    return {
        "service": settings.app_name,
        "environment": settings.app_env.value,
        "version": "1.0.0",
        "phase": "11 — production hardening & deployment preparation",
        "debug": settings.debug,
        "demo_mode": settings.demo_mode,
        "checks": checks,
    }
