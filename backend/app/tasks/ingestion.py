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
from app.ingestion.chunking import ChunkGenerator, ReportContext, SectionInput
from app.ingestion.pdf_parser import parse_pdf
from app.ingestion.section_detection import SectionDetector
from app.ingestion.storage import get_storage
from app.repositories.report_repository import SyncReportRepository
from app.retrieval.embeddings import (
    EmbeddingProviderError,
    EmbeddingService,
    GeminiEmbeddingProvider,
)
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

            # Chain into Phase 1B section detection (separate task / status).
            detect_sections.delay(report_id)

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


@celery_app.task(name="app.tasks.ingestion.detect_sections", acks_late=True)
def detect_sections(report_id: str) -> dict:
    """Detect logical sections for a processed report (Phase 1B).

    Workflow: load report → SECTIONING → load pages → rule-based detect →
    normalize → store sections → SECTIONED. On error: FAILED + recorded reason.
    Deterministic and LLM-free.
    """
    rid = uuid.UUID(report_id)
    log.info("sectioning.start", report_id=report_id)

    with SyncSessionLocal() as session:
        repo = SyncReportRepository(session)
        report = repo.get_report(rid)
        if report is None:
            log.warning("sectioning.report_missing", report_id=report_id)
            return {"report_id": report_id, "status": "MISSING"}

        try:
            pages = repo.get_pages_ordered(rid)
            if not pages:
                raise ValueError("no pages to section (report not processed?)")

            repo.mark_sectioning(report)

            detector = SectionDetector()
            detected = detector.detect(pages, report_type=str(report.report_type.value))
            rows = [
                {
                    "section_name": d.section_name,
                    "normalized_section_name": d.normalized_section_name,
                    "start_page": d.start_page,
                    "end_page": d.end_page,
                    "content": d.content,
                    "confidence_score": d.confidence_score,
                }
                for d in detected
            ]
            count = repo.replace_sections(rid, rows)
            repo.mark_sectioned(report)

            log.info("sectioning.success", report_id=report_id, sections=count)

            # Chain into Phase 1C chunk generation.
            generate_chunks.delay(report_id)

            return {"report_id": report_id, "status": "SECTIONED", "sections": count}

        except Exception as exc:  # noqa: BLE001 - record as FAILED, log, no crash-loop
            log.error("sectioning.failure", report_id=report_id, error=str(exc))
            session.rollback()
            failed = repo.get_report(rid)
            if failed is not None:
                repo.mark_failed(failed, message=f"{type(exc).__name__}: {exc}")
            return {"report_id": report_id, "status": "FAILED", "error": str(exc)}


@celery_app.task(name="app.tasks.ingestion.generate_chunks", acks_late=True)
def generate_chunks(report_id: str) -> dict:
    """Generate retrieval-ready chunks from a report's sections (Phase 1C).

    Workflow: load report → CHUNKING → load sections → section-aware recursive
    chunking + metadata + validation → store chunks → CHUNKED. On error: FAILED +
    recorded reason. Deterministic and LLM-free (no embeddings, no retrieval).
    """
    rid = uuid.UUID(report_id)
    log.info("chunking.start", report_id=report_id)

    with SyncSessionLocal() as session:
        repo = SyncReportRepository(session)
        report = repo.get_report(rid)
        if report is None:
            log.warning("chunking.report_missing", report_id=report_id)
            return {"report_id": report_id, "status": "MISSING"}

        try:
            sections = repo.get_sections_ordered(rid)
            if not sections:
                raise ValueError("no sections to chunk (report not sectioned?)")

            repo.mark_chunking(report)

            company = repo.get_company(report.company_id)
            report_ctx = ReportContext(
                report_id=str(report.id),
                report_type=str(report.report_type.value),
                year=report.year,
                quarter=report.quarter,
                company=(company.ticker or company.name) if company else None,
            )
            section_inputs = [
                SectionInput(
                    section_id=str(s.id),
                    section_name=s.section_name,
                    normalized_section_name=s.normalized_section_name,
                    start_page=s.start_page,
                    end_page=s.end_page,
                    content=s.content,
                )
                for s in sections
            ]

            generated = ChunkGenerator().generate(report_ctx, section_inputs)
            rows = [
                {
                    "section_id": uuid.UUID(g.section_id) if g.section_id else None,
                    "chunk_index": g.chunk_index,
                    "chunk_text": g.chunk_text,
                    "token_count": g.token_count,
                    "start_page": g.start_page,
                    "end_page": g.end_page,
                    "chunk_metadata": g.metadata,
                }
                for g in generated
            ]
            count = repo.replace_chunks(rid, rows)
            repo.mark_chunked(report)

            log.info("chunking.success", report_id=report_id, chunks=count)
            # NOTE: embedding generation (Phase 2A) is NOT auto-chained here. It
            # calls a paid external API, so it is an explicit operational action
            # triggered via POST /reports/{id}/embeddings/generate. This keeps the
            # deterministic ingestion pipeline offline-testable and avoids
            # unplanned API spend on every upload.
            return {"report_id": report_id, "status": "CHUNKED", "chunks": count}

        except Exception as exc:  # noqa: BLE001 - record as FAILED, log, no crash-loop
            log.error("chunking.failure", report_id=report_id, error=str(exc))
            session.rollback()
            failed = repo.get_report(rid)
            if failed is not None:
                repo.mark_failed(failed, message=f"{type(exc).__name__}: {exc}")
            return {"report_id": report_id, "status": "FAILED", "error": str(exc)}


@celery_app.task(
    bind=True,
    name="app.tasks.ingestion.generate_embeddings_task",
    acks_late=True,
    max_retries=3,
    default_retry_delay=30,
)
def generate_embeddings_task(self, report_id: str, *, force: bool = False) -> dict:
    """Generate + store Gemini embeddings for a report's chunks (Phase 2A).

    Workflow: load report → EMBEDDING → load chunks needing embeddings →
    batch-generate via Gemini → validate → store vector + mark COMPLETED →
    EMBEDDED (iff every chunk now has a vector). Idempotent: re-running only
    embeds chunks still missing a vector.

    Retry support: a transient provider failure that escapes the provider's own
    in-batch retries triggers a bounded Celery retry of the whole (idempotent)
    run. Permanent failures (config, no chunks, partial chunk failures) are
    recorded as FAILED with a reason — no crash-loop.
    """
    rid = uuid.UUID(report_id)
    log.info("embedding.task_start", report_id=report_id, force=force)

    with SyncSessionLocal() as session:
        repo = SyncReportRepository(session)
        report = repo.get_report(rid)
        if report is None:
            log.warning("embedding.report_missing", report_id=report_id)
            return {"report_id": report_id, "status": "MISSING"}

        try:
            provider = GeminiEmbeddingProvider.from_settings()
            service = EmbeddingService(repo, provider)
            metrics = service.generate_for_report(rid, force=force)

            if metrics.failed > 0:
                # Partial failure: record it so operators see it; a re-run (or the
                # generate endpoint) retries only the still-missing chunks.
                msg = f"{metrics.failed}/{metrics.total_chunks} chunks failed embedding"
                log.error("embedding.partial_failure", report_id=report_id, **metrics.as_dict())
                failed = repo.get_report(rid)
                if failed is not None:
                    repo.mark_failed(failed, message=msg)
                return {"report_id": report_id, "status": "FAILED", **metrics.as_dict()}

            log.info("embedding.task_success", report_id=report_id, **metrics.as_dict())
            return {"report_id": report_id, "status": "EMBEDDED", **metrics.as_dict()}

        except EmbeddingProviderError as exc:
            session.rollback()
            if getattr(exc, "retryable", False) and self.request.retries < self.max_retries:
                log.warning(
                    "embedding.task_retry",
                    report_id=report_id,
                    attempt=self.request.retries + 1,
                    error=str(exc),
                )
                raise self.retry(exc=exc)  # noqa: B904 - Celery retry idiom (re-raises Retry)
            log.error("embedding.task_failure", report_id=report_id, error=str(exc))
            failed = repo.get_report(rid)
            if failed is not None:
                repo.mark_failed(failed, message=f"{type(exc).__name__}: {exc}")
            return {"report_id": report_id, "status": "FAILED", "error": str(exc)}

        except Exception as exc:  # noqa: BLE001 - record as FAILED, log, no crash-loop
            log.error("embedding.task_failure", report_id=report_id, error=str(exc))
            session.rollback()
            failed = repo.get_report(rid)
            if failed is not None:
                repo.mark_failed(failed, message=f"{type(exc).__name__}: {exc}")
            return {"report_id": report_id, "status": "FAILED", "error": str(exc)}
