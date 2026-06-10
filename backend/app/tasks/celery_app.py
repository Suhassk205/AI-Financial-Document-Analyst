"""Celery application — async processing foundation (ADR-008: Redis + Celery).

This defines the Celery app, its queues, task routing, and global retry defaults.
NO TASKS ARE REGISTERED YET. Document-processing tasks (parse, chunk, embed,
extract) are added in Phase 1+ under `app/tasks/` and routed to the queues below.

Worker (see docker-compose `worker` service):
    celery -A app.tasks.celery_app.celery_app worker -Q default,ingestion,extraction
"""

from __future__ import annotations

from celery import Celery
from kombu import Queue

from app.core.config import settings
from app.core.logging import configure_logging

# Ensure workers emit logs through the same structured pipeline as the API.
configure_logging()

celery_app = Celery(
    "fda",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    # Task modules registered with the worker (Phase 1A: ingestion).
    include=["app.tasks.ingestion"],
)

# ---------------------------------------------------------------------------
# Queues — work is segregated so heavy ingestion can scale independently of
# lighter extraction work, and neither starves default/control tasks.
# ---------------------------------------------------------------------------
celery_app.conf.task_queues = (
    Queue("default"),       # misc/control tasks
    Queue("ingestion"),     # parse → chunk → embed (I/O + API heavy)
    Queue("extraction"),    # metric / risk / tone extraction (LLM heavy)
)
celery_app.conf.task_default_queue = "default"

# ---------------------------------------------------------------------------
# Task routing — map task name globs to queues. Concrete task names are added
# alongside their implementations in later phases.
# Example (future):
#   "app.tasks.ingestion.*":  {"queue": "ingestion"}
#   "app.tasks.extraction.*": {"queue": "extraction"}
# ---------------------------------------------------------------------------
celery_app.conf.task_routes = {
    "app.tasks.ingestion.*": {"queue": "ingestion"},
    "app.tasks.extraction.*": {"queue": "extraction"},
}

# ---------------------------------------------------------------------------
# Global behavior & retry strategy (see docs/08_INFRASTRUCTURE_SETUP.md).
# ---------------------------------------------------------------------------
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Reliability: ack only after completion so a crashed worker re-queues the task.
    task_acks_late=True,
    worker_prefetch_multiplier=1,        # fair dispatch for long-running tasks
    task_track_started=True,
    # Default retry policy for tasks that opt into autoretry (per-task overrides allowed).
    task_default_retry_delay=10,         # seconds before first retry
    task_max_retries=3,                  # exponential backoff configured per task
    result_expires=60 * 60 * 24,         # results live 24h in the backend
)
