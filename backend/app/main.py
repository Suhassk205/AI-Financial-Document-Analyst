"""FastAPI application entrypoint (Phase 0.5 foundation).

Wires together: structured logging, CORS, a request-id middleware (for traceable
logs), the v1 router, and lifespan startup/shutdown. NO business endpoints are
mounted — only operational ones (/health, /ready, /status).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging, get_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown hooks. Configure logging once; clean up on exit."""
    configure_logging()
    log = get_logger(__name__)
    log.info("app.startup", env=settings.app_env.value, name=settings.app_name)
    yield
    log.info("app.shutdown")


app = FastAPI(
    title="AI Financial Document Analyst",
    version="0.0.1",
    description="Grounded, citation-backed financial document analysis. (Phase 0.5 foundation)",
    lifespan=lifespan,
)

# ---- CORS --------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Request-id middleware ---------------------------------------------------
@app.middleware("http")
async def request_context_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Attach a request id, bind it to logs, echo it back as `X-Request-Id`."""
    request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
    structlog.contextvars.bind_contextvars(request_id=request_id)
    try:
        response = await call_next(request)
    finally:
        structlog.contextvars.clear_contextvars()
    response.headers["X-Request-Id"] = request_id
    return response


# ---- Exception handling ------------------------------------------------------
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Translate domain errors into the standard error envelope (docs/04 §5)."""
    request_id = request.headers.get("X-Request-Id")
    get_logger(__name__).warning(
        "app_error", code=exc.code, status=exc.status_code, message=exc.message
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "request_id": request_id,
            }
        },
    )


# ---- Routers -----------------------------------------------------------------
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {
        "service": settings.app_name,
        "docs": "/docs",
        "health": f"{settings.api_v1_prefix}/health",
    }
