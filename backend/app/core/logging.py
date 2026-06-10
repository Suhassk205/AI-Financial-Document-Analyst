"""Centralized, structured logging configuration (structlog).

A single `configure_logging()` call wires both stdlib `logging` and `structlog`
so that:
  * application logs, API logs, and Celery worker logs share one pipeline,
  * output is JSON in production (observability-friendly) and human-readable in dev,
  * a `request_id` (and other bound context) is carried through log records.

No business logging is implemented here — only the foundation. Call
`configure_logging()` once at process start (FastAPI lifespan and Celery init).
"""

from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import LogFormat, settings


def configure_logging() -> None:
    """Configure stdlib logging + structlog. Idempotent."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Shared processors applied to every event before rendering.
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,  # carries bound request_id, etc.
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.log_format == LogFormat.JSON:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging (uvicorn, sqlalchemy, celery) through the same level.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )
    for noisy in ("uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(
            logging.WARNING if not settings.debug else logging.INFO
        )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger. Use module `__name__` as the name."""
    return structlog.get_logger(name)
