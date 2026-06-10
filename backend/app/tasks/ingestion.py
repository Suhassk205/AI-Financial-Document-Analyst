"""Ingestion Celery tasks (Phase 1A).

`process_report` is the single task: load the report, parse its PDF, persist the
extracted pages, and update status. Runs synchronously on a Celery worker using
a sync DB session (see app.db.session).

Routing: the task name `app.tasks.ingestion.process_report` matches the
`app.tasks.ingestion.*` route → `ingestion` queue (app.tasks.celery_app).
"""

from __future__ import annotations

import uuid

from app.core.logging import get_logger
from app.db.session import SyncSessionLocal
from app.ingestion.pdf_parser import parse_pdf
from app.ingestion.storage import get_storage
from app.repositories.report_repository import SyncReportRepository
from app.tasks.celery_app import celery_app

log = get_logger(__name__)


@celery_app.task(name="app.tasks.ingestion.process_report", acks_late=True)
def process_report(report_id: str) -> dict:
    """Parse a report's PDF and persist its pages.

    Workflow: load report → PROCESSING → parse PDF → store pages → PROCESSED.
    On failure: status=FAILED with the reason recorded on the report and logged.

    Failures here are treated as handled business outcomes (a corrupt/unreadable
    PDF is deterministic — retrying would not help), so the task records FAILED
    and returns rather than crashing into an unbounded retry loop. Transient-error
    retry policy can be layered on in a later phase if needed.
    """
    rid = uuid.UUID(report_id)
    log.info("processing.start", report_id=report_id)

    with SyncSessionLocal() as session:
        repo = SyncReportRepository(session)
        report = repo.get_report(rid)
        if report is None:
            log.warning("processing.report_missing", report_id=report_id)
            return {"report_id": report_id, "status": "MISSING"}

        try:
            repo.mark_processing(report)

            abs_path = get_storage().get_absolute_path(report.storage_path)
            parsed = parse_pdf(abs_path)

            page_rows = [(p.page_number, p.text) for p in parsed.pages]
            repo.replace_pages(rid, page_rows)
            repo.mark_processed(report, total_pages=parsed.total_pages)

            log.info("processing.success", report_id=report_id, total_pages=parsed.total_pages)
            return {
                "report_id": report_id,
                "status": "PROCESSED",
                "total_pages": parsed.total_pages,
            }

        except Exception as exc:  # noqa: BLE001 - record as FAILED, log, do not crash-loop
            log.error("processing.failure", report_id=report_id, error=str(exc))
            session.rollback()
            failed = repo.get_report(rid)
            if failed is not None:
                repo.mark_failed(failed, message=f"{type(exc).__name__}: {exc}")
            return {"report_id": report_id, "status": "FAILED", "error": str(exc)}
