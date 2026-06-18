"""Ingestion Celery tasks (Phase 1A).

`process_report` is the single task: load the report, parse its PDF, persist the
extracted pages, and update status. Runs synchronously on a Celery worker using
a sync DB session (see app.db.session).

Routing: the task name `app.tasks.ingestion.process_report` matches the
`app.tasks.ingestion.*` route → `ingestion` queue (app.tasks.celery_app).
"""

from __future__ import annotations

import sys
import uuid

from app.core.logging import get_logger
from app.db.session import SyncSessionLocal
from app.financial.comparison import ComparisonService, MetricPoint
from app.financial.analytics import AnalyticsBuilder
from app.financial.extraction import ChunkInput, HybridExtractor
from app.ingestion.chunking import ChunkGenerator, ReportContext, SectionInput
from app.models.financial_metric import FinancialMetric
from app.ingestion.pdf_parser import parse_pdf
from app.ingestion.section_detection import SectionDetector
from app.ingestion.storage import get_storage
from app.repositories.report_repository import SyncReportRepository
from app.retrieval.embeddings import (
    EmbeddingProviderError,
    EmbeddingService,
    GeminiEmbeddingProvider,
)
from app.risk.extraction.extraction_models import RiskChunkInput
from app.risk.extraction.hybrid_extractor import HybridRiskExtractor
from app.risk.evolution.evolution_service import RiskEvolutionService
from app.tone.analysis.hybrid_analyzer import HybridToneAnalyzer
from app.tone.analysis.models import ToneChunkInput
from app.tone.evolution.evolution_service import ToneEvolutionService
from app.tasks.celery_app import celery_app

# Canonical sections that carry financial metrics (candidate set for extraction).
METRIC_CANDIDATE_SECTIONS = (
    "Income Statement", "Financial Statements", "Balance Sheet", "Cash Flow Statement",
    "Notes to Financial Statements", "MD&A", "Forward Guidance", "Management Commentary",
)

# Canonical sections that carry risk disclosures.
RISK_CANDIDATE_SECTIONS = (
    "Risk Factors", "MD&A", "Forward Guidance", "Forward-Looking Statements",
)

# Canonical sections that carry management tone.
TONE_CANDIDATE_SECTIONS = (
    "Management Commentary", "CEO Commentary", "CFO Commentary", "Prepared Remarks",
    "Question & Answer", "Forward Guidance", "MD&A", "Shareholder Letters",
)

log = get_logger(__name__)
STAGE_ORDER = [
    "PROCESSED",
    "SECTIONED",
    "CHUNKED",
    "EMBEDDED",
    "METRICS_READY",
    "COMPARISON_READY",
    "ANALYTICS_READY",
    "RISKS_READY",
    "READY",
]


def is_testing() -> bool:
    return "pytest" in sys.modules


def is_mocked(func) -> bool:
    from unittest.mock import Mock
    return isinstance(func, Mock) or hasattr(func, "assert_called") or hasattr(func, "called")


def is_stage_completed(completed_stage: str | None, target_stage: str) -> bool:
    if completed_stage is None:
        return False
    if completed_stage not in STAGE_ORDER:
        return False
    return STAGE_ORDER.index(completed_stage) >= STAGE_ORDER.index(target_stage)


def handle_task_failure_or_retry(task, report_id: str | uuid.UUID, stage_name: str, exc: Exception) -> None:
    """Shared helper to record progress metadata directly into PostgreSQL and trigger Celery retries."""
    rid = uuid.UUID(str(report_id))
    log.warning("task.failure_or_retry", stage=stage_name, report_id=str(rid), error=str(exc))
    
    with SyncSessionLocal() as session:
        repo = SyncReportRepository(session)
        report = repo.get_report(rid)
        if report is not None:
            report.failed_stage = stage_name
            report.error_message = f"{type(exc).__name__}: {exc}"[:2000]
            session.commit()
            
    if not is_testing() and task.request.retries < task.max_retries:
        with SyncSessionLocal() as session:
            repo = SyncReportRepository(session)
            report = repo.get_report(rid)
            if report is not None:
                report.retry_count = task.request.retries + 1
                session.commit()
        raise task.retry(exc=exc)
    else:
        with SyncSessionLocal() as session:
            repo = SyncReportRepository(session)
            report = repo.get_report(rid)
            if report is not None:
                repo.mark_failed(report, message=f"{type(exc).__name__}: {exc}", failed_stage=stage_name)


@celery_app.task(
    bind=True,
    name="app.tasks.ingestion.process_report",
    acks_late=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def process_report(self, report_id: str) -> dict:
    """Parse a report's PDF and persist its pages."""
    rid = uuid.UUID(report_id)
    log.info("processing.start", report_id=report_id)

    with SyncSessionLocal() as session:
        repo = SyncReportRepository(session)
        report = repo.get_report(rid)
        if report is None:
            log.warning("processing.report_missing", report_id=report_id)
            return {"report_id": report_id, "status": "MISSING"}

        if report.completed_stage and is_stage_completed(report.completed_stage, "PROCESSED"):
            log.info("processing.skip", report_id=report_id, completed_stage=report.completed_stage)
            if not is_testing() or is_mocked(detect_sections.delay):
                detect_sections.delay(report_id)
            return {"report_id": report_id, "status": "SKIPPED_PROCESSED", "total_pages": report.total_pages}

        import tempfile
        from pathlib import Path

        tmp_path = None
        try:
            repo.mark_processing(report)

            if report.file_data is not None:
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(report.file_data)
                    tmp_path = Path(tmp.name)
                parsed = parse_pdf(tmp_path)
            else:
                abs_path = get_storage().get_absolute_path(report.storage_path)
                parsed = parse_pdf(abs_path)

            page_rows = [(p.page_number, p.text) for p in parsed.pages]
            repo.replace_pages(rid, page_rows)

            report.file_data = None
            repo.mark_processed(report, total_pages=parsed.total_pages)

            log.info("processing.success", report_id=report_id, total_pages=parsed.total_pages)
            if not is_testing() or is_mocked(detect_sections.delay):
                detect_sections.delay(report_id)

            return {
                "report_id": report_id,
                "status": "PROCESSED",
                "total_pages": parsed.total_pages,
            }

        except Exception as exc:
            session.rollback()
            handle_task_failure_or_retry(self, rid, "PROCESSED", exc)
            return {"report_id": report_id, "status": "FAILED", "error": str(exc)}
        finally:
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception as cleanup_exc:
                    log.warning("processing.tmp_cleanup_failed", path=str(tmp_path), error=str(cleanup_exc))


@celery_app.task(
    bind=True,
    name="app.tasks.ingestion.detect_sections",
    acks_late=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def detect_sections(self, report_id: str) -> dict:
    """Detect logical sections for a processed report (Phase 1B)."""
    rid = uuid.UUID(report_id)
    log.info("sectioning.start", report_id=report_id)

    with SyncSessionLocal() as session:
        repo = SyncReportRepository(session)
        report = repo.get_report(rid)
        if report is None:
            log.warning("sectioning.report_missing", report_id=report_id)
            return {"report_id": report_id, "status": "MISSING"}

        if report.completed_stage and is_stage_completed(report.completed_stage, "SECTIONED"):
            log.info("sectioning.skip", report_id=report_id, completed_stage=report.completed_stage)
            if not is_testing() or is_mocked(generate_chunks.delay):
                generate_chunks.delay(report_id)
            from app.models.report_section import ReportSection
            sections_count = session.query(ReportSection).filter(ReportSection.report_id == rid).count()
            return {"report_id": report_id, "status": "SKIPPED_SECTIONED", "sections": sections_count}

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
            if not is_testing() or is_mocked(generate_chunks.delay):
                generate_chunks.delay(report_id)

            return {"report_id": report_id, "status": "SECTIONED", "sections": count}

        except Exception as exc:
            session.rollback()
            handle_task_failure_or_retry(self, rid, "SECTIONED", exc)
            return {"report_id": report_id, "status": "FAILED", "error": str(exc)}


@celery_app.task(
    bind=True,
    name="app.tasks.ingestion.generate_chunks",
    acks_late=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def generate_chunks(self, report_id: str) -> dict:
    """Generate retrieval-ready chunks from a report's sections (Phase 1C)."""
    rid = uuid.UUID(report_id)
    log.info("chunking.start", report_id=report_id)

    with SyncSessionLocal() as session:
        repo = SyncReportRepository(session)
        report = repo.get_report(rid)
        if report is None:
            log.warning("chunking.report_missing", report_id=report_id)
            return {"report_id": report_id, "status": "MISSING"}

        if report.completed_stage and is_stage_completed(report.completed_stage, "CHUNKED"):
            log.info("chunking.skip", report_id=report_id, completed_stage=report.completed_stage)
            if not is_testing() or is_mocked(generate_embeddings_task.delay):
                generate_embeddings_task.delay(report_id)
            from app.models.document_chunk import DocumentChunk
            chunks_count = session.query(DocumentChunk).filter(DocumentChunk.report_id == rid).count()
            return {"report_id": report_id, "status": "SKIPPED_CHUNKED", "chunks": chunks_count}

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
            if not is_testing() or is_mocked(generate_embeddings_task.delay):
                generate_embeddings_task.delay(report_id)

            return {"report_id": report_id, "status": "CHUNKED", "chunks": count}

        except Exception as exc:
            session.rollback()
            handle_task_failure_or_retry(self, rid, "CHUNKED", exc)
            return {"report_id": report_id, "status": "FAILED", "error": str(exc)}


@celery_app.task(
    bind=True,
    name="app.tasks.ingestion.generate_embeddings_task",
    acks_late=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def generate_embeddings_task(self, report_id: str, *, force: bool = False) -> dict:
    """Generate + store Gemini embeddings for a report's chunks (Phase 2A)."""
    rid = uuid.UUID(report_id)
    log.info("embedding.task_start", report_id=report_id, force=force)

    with SyncSessionLocal() as session:
        repo = SyncReportRepository(session)
        report = repo.get_report(rid)
        if report is None:
            log.warning("embedding.report_missing", report_id=report_id)
            return {"report_id": report_id, "status": "MISSING"}

        if not force and report.completed_stage and is_stage_completed(report.completed_stage, "EMBEDDED"):
            log.info("embedding.skip", report_id=report_id, completed_stage=report.completed_stage)
            if not is_testing() or is_mocked(extract_financial_metrics_task.delay):
                extract_financial_metrics_task.delay(report_id)
            from app.models.document_chunk import DocumentChunk
            total = session.query(DocumentChunk).filter(DocumentChunk.report_id == rid).count()
            embedded = session.query(DocumentChunk).filter(
                DocumentChunk.report_id == rid,
                DocumentChunk.chunk_vector.isnot(None)
            ).count()
            failed = total - embedded
            return {
                "report_id": report_id,
                "status": "SKIPPED_EMBEDDED",
                "total_chunks": total,
                "embedded": embedded,
                "failed": failed,
            }

        try:
            repo.mark_embedding(report)
            provider = GeminiEmbeddingProvider.from_settings()
            service = EmbeddingService(repo, provider)
            metrics = service.generate_for_report(rid, force=force)

            if metrics.failed > 0:
                msg = f"{metrics.failed}/{metrics.total_chunks} chunks failed embedding"
                log.error("embedding.partial_failure", report_id=report_id, **metrics.as_dict())
                raise EmbeddingProviderError(msg, retryable=True)

            repo.mark_embedded(report)
            log.info("embedding.task_success", report_id=report_id, **metrics.as_dict())
            if not is_testing() or is_mocked(extract_financial_metrics_task.delay):
                extract_financial_metrics_task.delay(report_id)

            return {"report_id": report_id, "status": "EMBEDDED", **metrics.as_dict()}

        except Exception as exc:
            session.rollback()
            handle_task_failure_or_retry(self, rid, "EMBEDDED", exc)
            return {"report_id": report_id, "status": "FAILED", "error": str(exc)}


@celery_app.task(
    bind=True,
    name="app.tasks.extraction.extract_financial_metrics_task",
    acks_late=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def extract_financial_metrics_task(self, report_id: str) -> dict:
    """Extract structured financial metrics from a report's chunks (Phase 3A)."""
    rid = uuid.UUID(report_id)
    log.info("extraction.task_start", report_id=report_id)

    with SyncSessionLocal() as session:
        repo = SyncReportRepository(session)
        report = repo.get_report(rid)
        if report is None:
            log.warning("extraction.report_missing", report_id=report_id)
            return {"report_id": report_id, "status": "MISSING"}

        if report.completed_stage and is_stage_completed(report.completed_stage, "METRICS_READY"):
            log.info("extraction.skip", report_id=report_id, completed_stage=report.completed_stage)
            if not is_testing() or is_mocked(generate_metric_comparisons_task.delay):
                generate_metric_comparisons_task.delay(report_id)
            metrics_count = len(repo.get_report_metrics(rid))
            return {"report_id": report_id, "status": "SKIPPED_METRICS_READY", "metrics": metrics_count}

        try:
            chunks = repo.get_extraction_chunks(rid, METRIC_CANDIDATE_SECTIONS)
            if not chunks:
                raise ValueError("no candidate chunks to extract (report not chunked?)")

            repo.mark_extracting(report)

            inputs = [
                ChunkInput(
                    chunk_id=str(c.id),
                    text=c.chunk_text,
                    normalized_section_name=(c.chunk_metadata or {}).get(
                        "normalized_section_name"
                    ),
                    fiscal_year=report.year,
                    fiscal_quarter=report.quarter,
                )
                for c in chunks
            ]

            result = HybridExtractor().extract(inputs)
            rows = [
                {
                    "source_chunk_id": uuid.UUID(m.source_chunk_id) if m.source_chunk_id else None,
                    "metric_name": m.metric_name,
                    "normalized_metric_name": m.normalized_metric_name,
                    "metric_category": m.category,
                    "value": m.value,
                    "currency": m.currency,
                    "unit": m.unit,
                    "fiscal_year": m.fiscal_year,
                    "fiscal_quarter": m.fiscal_quarter,
                    "confidence_score": m.confidence_score,
                    "extraction_method": m.extraction_method,
                    "source_text": m.source_text,
                    "extraction_metadata": m.extraction_metadata,
                }
                for m in result.metrics
            ]
            count = repo.replace_metrics(rid, rows)
            repo.mark_extracted(report)

            log.info(
                "extraction.task_success", report_id=report_id, metrics=count, **result.stats.as_dict()
            )
            if not is_testing() or is_mocked(generate_metric_comparisons_task.delay):
                generate_metric_comparisons_task.delay(report_id)

            return {"report_id": report_id, "status": "METRICS_READY", "metrics": count, **result.stats.as_dict()}

        except Exception as exc:
            session.rollback()
            handle_task_failure_or_retry(self, rid, "METRICS_READY", exc)
            return {"report_id": report_id, "status": "FAILED", "error": str(exc)}


def _to_point(m: FinancialMetric) -> MetricPoint:
    return MetricPoint(
        metric_id=str(m.id),
        normalized_metric_name=m.normalized_metric_name,
        value=m.value,
        fiscal_year=m.fiscal_year,
        fiscal_quarter=m.fiscal_quarter,
        confidence=float(m.confidence_score),
    )


@celery_app.task(
    bind=True,
    name="app.tasks.extraction.generate_metric_comparisons_task",
    acks_late=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def generate_metric_comparisons_task(self, report_id: str) -> dict:
    """Generate deterministic period comparisons for a report's metrics (Phase 3B)."""
    rid = uuid.UUID(report_id)
    log.info("comparison.task_start", report_id=report_id)

    with SyncSessionLocal() as session:
        repo = SyncReportRepository(session)
        report = repo.get_report(rid)
        if report is None:
            log.warning("comparison.report_missing", report_id=report_id)
            return {"report_id": report_id, "status": "MISSING"}

        if report.completed_stage and is_stage_completed(report.completed_stage, "COMPARISON_READY"):
            log.info("comparison.skip", report_id=report_id, completed_stage=report.completed_stage)
            if not is_testing() or is_mocked(generate_financial_analytics_task.delay):
                generate_financial_analytics_task.delay(report_id)
            from app.models.financial_metric import FinancialMetric
            from app.models.metric_comparison import MetricComparison
            metric_ids = session.query(FinancialMetric.id).filter(FinancialMetric.report_id == rid)
            comparisons_count = session.query(MetricComparison).filter(MetricComparison.metric_id.in_(metric_ids)).count()
            return {"report_id": report_id, "status": "SKIPPED_COMPARISON_READY", "comparisons": comparisons_count}

        try:
            repo.mark_comparing(report)

            if report.company_id is None:
                repo.replace_report_comparisons(rid, [])
                repo.mark_compared(report)
                log.info("comparison.no_company", report_id=report_id)
                if not is_testing() or is_mocked(generate_financial_analytics_task.delay):
                    generate_financial_analytics_task.delay(report_id)
                return {"report_id": report_id, "status": "COMPARISON_READY", "comparisons": 0}

            company_points = [_to_point(m) for m in repo.get_company_metrics(report.company_id)]
            current_points = [_to_point(m) for m in repo.get_report_metrics(rid)]

            result = ComparisonService().build_comparisons(
                current_points, company_points, str(report.company_id)
            )
            rows = [
                {
                    "metric_id": uuid.UUID(r.metric_id),
                    "company_id": uuid.UUID(r.company_id),
                    "metric_name": r.metric_name,
                    "comparison_type": r.comparison_type,
                    "current_period": r.current_period,
                    "previous_period": r.previous_period,
                    "current_value": r.current_value,
                    "previous_value": r.previous_value,
                    "absolute_change": r.absolute_change,
                    "percentage_change": r.percentage_change,
                }
                for r in result.rows
            ]
            count = repo.replace_report_comparisons(rid, rows)
            repo.mark_compared(report)

            log.info(
                "comparison.task_success", report_id=report_id, comparisons=count,
                **result.stats.as_dict(),
            )
            if not is_testing() or is_mocked(generate_financial_analytics_task.delay):
                generate_financial_analytics_task.delay(report_id)

            return {"report_id": report_id, "status": "COMPARISON_READY", "comparisons": count, **result.stats.as_dict()}

        except Exception as exc:
            session.rollback()
            handle_task_failure_or_retry(self, rid, "COMPARISON_READY", exc)
            return {"report_id": report_id, "status": "FAILED", "error": str(exc)}


@celery_app.task(
    bind=True,
    name="app.tasks.extraction.generate_financial_analytics_task",
    acks_late=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def generate_financial_analytics_task(self, report_id: str) -> dict:
    """Generate ratios, signals, and trend classifications for a report (Phase 3C)."""
    rid = uuid.UUID(report_id)
    log.info("analytics.task_start", report_id=report_id)

    with SyncSessionLocal() as session:
        repo = SyncReportRepository(session)
        report = repo.get_report(rid)
        if report is None:
            log.warning("analytics.report_missing", report_id=report_id)
            return {"report_id": report_id, "status": "MISSING"}

        if report.completed_stage and is_stage_completed(report.completed_stage, "ANALYTICS_READY"):
            log.info("analytics.skip", report_id=report_id, completed_stage=report.completed_stage)
            if not is_testing() or is_mocked(extract_risks_task.delay):
                extract_risks_task.delay(report_id)
            from app.models.financial_analytics import FinancialAnalytics
            analytics_count = session.query(FinancialAnalytics).filter(FinancialAnalytics.report_id == rid).count()
            return {"report_id": report_id, "status": "SKIPPED_ANALYTICS_READY", "analytics": analytics_count}

        try:
            repo.mark_analyzing(report)

            if report.company_id is None:
                repo.replace_report_analytics(rid, [])
                repo.mark_analyzed(report)
                log.info("analytics.no_company", report_id=report_id)
                if not is_testing() or is_mocked(extract_risks_task.delay):
                    extract_risks_task.delay(report_id)
                return {"report_id": report_id, "status": "ANALYTICS_READY", "analytics": 0}

            metrics = repo.get_report_metrics(rid)
            comparisons = repo.get_company_comparisons(report.company_id)
            
            # Filter comparisons to only those anchored to this report's metrics
            report_metric_ids = {m.id for m in metrics}
            report_comparisons = [c for c in comparisons if c.metric_id in report_metric_ids]

            # Get historical metrics for guidance comparisons
            company_metrics = repo.get_company_metrics(report.company_id)

            db_rows, warnings = AnalyticsBuilder().build_analytics(
                company_id=report.company_id,
                report_id=rid,
                metrics=metrics,
                comparisons=report_comparisons,
                company_historical_metrics=company_metrics,
            )

            count = repo.replace_report_analytics(rid, db_rows)
            repo.mark_analyzed(report)

            log.info(
                "analytics.task_success", report_id=report_id, analytics=count,
                warnings=len(warnings),
            )
            if not is_testing() or is_mocked(extract_risks_task.delay):
                extract_risks_task.delay(report_id)

            return {"report_id": report_id, "status": "ANALYTICS_READY", "analytics": count, "warnings": len(warnings)}

        except Exception as exc:
            session.rollback()
            handle_task_failure_or_retry(self, rid, "ANALYTICS_READY", exc)
            return {"report_id": report_id, "status": "FAILED", "error": str(exc)}


@celery_app.task(
    bind=True,
    name="app.tasks.extraction.extract_risks_task",
    acks_late=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def extract_risks_task(self, report_id: str) -> dict:
    """Extract structured risk factors from a report's chunks (Phase 4)."""
    rid = uuid.UUID(report_id)
    log.info("risk_extraction.task_start", report_id=report_id)

    with SyncSessionLocal() as session:
        repo = SyncReportRepository(session)
        report = repo.get_report(rid)
        if report is None:
            log.warning("risk_extraction.report_missing", report_id=report_id)
            return {"report_id": report_id, "status": "MISSING"}

        if report.completed_stage and is_stage_completed(report.completed_stage, "RISKS_READY"):
            log.info("risk_extraction.skip", report_id=report_id, completed_stage=report.completed_stage)
            if not is_testing() or is_mocked(generate_risk_evolution_task.delay):
                generate_risk_evolution_task.delay(report_id)
            risks_count = len(repo.get_report_risks(rid))
            return {"report_id": report_id, "status": "SKIPPED_RISKS_READY", "risks": risks_count}

        try:
            chunks = repo.get_extraction_chunks(rid, RISK_CANDIDATE_SECTIONS)
            if not chunks:
                raise ValueError("no candidate chunks to extract risks (report not chunked?)")

            repo.mark_risk_extracting(report)

            inputs = [
                RiskChunkInput(
                    chunk_id=str(c.id),
                    text=c.chunk_text,
                    normalized_section_name=(c.chunk_metadata or {}).get(
                        "normalized_section_name"
                    ),
                    fiscal_year=report.year,
                    fiscal_quarter=report.quarter,
                )
                for c in chunks
            ]

            result = HybridRiskExtractor().extract(inputs)
            rows = [
                {
                    "company_id": report.company_id,
                    "source_chunk_id": uuid.UUID(r.source_chunk_id) if r.source_chunk_id else None,
                    "risk_name": r.risk_name,
                    "normalized_risk_name": r.normalized_risk_name,
                    "risk_description": r.risk_description,
                    "category": r.category,
                    "severity": r.severity,
                    "confidence_score": r.confidence_score,
                    "extraction_method": r.extraction_method,
                    "source_text": r.source_text,
                    "extraction_metadata": r.extraction_metadata,
                }
                for r in result.risks
            ]
            count = repo.replace_risks(rid, rows)

            log.info(
                "risk_extraction.task_success", report_id=report_id, risks=count, **result.stats.as_dict()
            )

            # Chain into Phase 4 risk evolution
            if not is_testing() or is_mocked(generate_risk_evolution_task.delay):
                generate_risk_evolution_task.delay(report_id)

            return {"report_id": report_id, "status": "RISK_EXTRACTED_PARTIAL", "risks": count, **result.stats.as_dict()}

        except Exception as exc:
            session.rollback()
            handle_task_failure_or_retry(self, rid, "RISKS_READY", exc)
            return {"report_id": report_id, "status": "FAILED", "error": str(exc)}


@celery_app.task(
    bind=True,
    name="app.tasks.extraction.generate_risk_evolution_task",
    acks_late=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def generate_risk_evolution_task(self, report_id: str) -> dict:
    """Generate risk evolution records comparing current risks to prior period (Phase 4)."""
    rid = uuid.UUID(report_id)
    log.info("risk_evolution.task_start", report_id=report_id)

    with SyncSessionLocal() as session:
        repo = SyncReportRepository(session)
        report = repo.get_report(rid)
        if report is None:
            log.warning("risk_evolution.report_missing", report_id=report_id)
            return {"report_id": report_id, "status": "MISSING"}

        if report.completed_stage and is_stage_completed(report.completed_stage, "RISKS_READY"):
            log.info("risk_evolution.skip", report_id=report_id, completed_stage=report.completed_stage)
            if not is_testing() or is_mocked(extract_management_tone_task.delay):
                extract_management_tone_task.delay(report_id)
            from app.models.risk_factor import RiskFactor
            from app.models.risk_evolution import RiskEvolution
            from sqlalchemy import or_, and_
            current_ids = session.query(RiskFactor.id).filter(RiskFactor.report_id == rid)
            prior_report = repo.get_prior_report(report)
            prior_report_id = prior_report.id if prior_report else None
            if prior_report_id:
                prior_ids = session.query(RiskFactor.id).filter(RiskFactor.report_id == prior_report_id)
                evolutions_count = session.query(RiskEvolution).filter(
                    RiskEvolution.company_id == report.company_id,
                    or_(
                        RiskEvolution.current_risk_id.in_(current_ids),
                        or_(
                            RiskEvolution.previous_risk_id.in_(current_ids),
                            and_(
                                RiskEvolution.previous_risk_id.in_(prior_ids),
                                RiskEvolution.current_risk_id.is_(None)
                            )
                        )
                    )
                ).count()
            else:
                evolutions_count = session.query(RiskEvolution).filter(
                    RiskEvolution.company_id == report.company_id,
                    or_(
                        RiskEvolution.current_risk_id.in_(current_ids),
                        RiskEvolution.previous_risk_id.in_(current_ids),
                    )
                ).count()
            return {"report_id": report_id, "status": "SKIPPED_RISKS_READY", "evolutions": evolutions_count}

        try:
            if report.company_id is None:
                repo.replace_risk_evolution(uuid.UUID("00000000-0000-0000-0000-000000000000"), rid, None, [])
                repo.mark_risk_extracted(report)
                log.info("risk_evolution.no_company", report_id=report_id)
                if not is_testing() or is_mocked(extract_management_tone_task.delay):
                    extract_management_tone_task.delay(report_id)
                return {"report_id": report_id, "status": "RISKS_READY", "evolutions": 0}

            prior_report = repo.get_prior_report(report)
            prior_report_id = prior_report.id if prior_report else None

            current_risks = repo.get_report_risks(rid)
            prior_risks = repo.get_report_risks(prior_report_id) if prior_report_id else []

            result = RiskEvolutionService().build_evolution(
                str(report.company_id),
                current_risks,
                prior_risks,
            )

            rows = [
                {
                    "current_risk_id": uuid.UUID(r.current_risk_id) if r.current_risk_id else None,
                    "previous_risk_id": uuid.UUID(r.previous_risk_id) if r.previous_risk_id else None,
                    "evolution_type": r.evolution_type,
                    "confidence_score": r.confidence_score,
                    "explanation": r.explanation,
                }
                for r in result.rows
            ]

            count = repo.replace_risk_evolution(
                report.company_id,
                rid,
                prior_report_id,
                rows,
            )
            repo.mark_risk_extracted(report)

            log.info(
                "risk_evolution.task_success",
                report_id=report_id,
                evolutions=count,
                **result.stats.as_dict(),
            )
            if not is_testing() or is_mocked(extract_management_tone_task.delay):
                extract_management_tone_task.delay(report_id)

            return {"report_id": report_id, "status": "RISKS_READY", "evolutions": count, **result.stats.as_dict()}

        except Exception as exc:
            session.rollback()
            handle_task_failure_or_retry(self, rid, "RISKS_READY", exc)
            return {"report_id": report_id, "status": "FAILED", "error": str(exc)}


@celery_app.task(
    bind=True,
    name="app.tasks.extraction.extract_management_tone_task",
    acks_late=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def extract_management_tone_task(self, report_id: str) -> dict:
    """Extract management tone and generate PoP evolution records (Phase 5)."""
    rid = uuid.UUID(report_id)
    log.info("tone_extraction.task_start", report_id=report_id)

    with SyncSessionLocal() as session:
        repo = SyncReportRepository(session)
        report = repo.get_report(rid)
        if report is None:
            log.warning("tone_extraction.report_missing", report_id=report_id)
            return {"report_id": report_id, "status": "MISSING"}

        if report.completed_stage and is_stage_completed(report.completed_stage, "READY"):
            log.info("tone_extraction.skip", report_id=report_id, completed_stage=report.completed_stage)
            tones_count = len(repo.get_report_tone(rid))
            from app.models.management_tone import ManagementTone
            from app.models.tone_evolution import ToneEvolution
            from sqlalchemy import or_, and_
            current_ids = session.query(ManagementTone.id).filter(ManagementTone.report_id == rid)
            prior_report = repo.get_prior_report(report)
            prior_report_id = prior_report.id if prior_report else None
            if prior_report_id:
                prior_ids = session.query(ManagementTone.id).filter(ManagementTone.report_id == prior_report_id)
                evolutions_count = session.query(ToneEvolution).filter(
                    ToneEvolution.company_id == report.company_id,
                    or_(
                        ToneEvolution.current_tone_id.in_(current_ids),
                        or_(
                            ToneEvolution.previous_tone_id.in_(current_ids),
                            and_(
                                ToneEvolution.previous_tone_id.in_(prior_ids),
                                ToneEvolution.current_tone_id.is_(None)
                            )
                        )
                    )
                ).count()
            else:
                evolutions_count = session.query(ToneEvolution).filter(
                    ToneEvolution.company_id == report.company_id,
                    or_(
                        ToneEvolution.current_tone_id.in_(current_ids),
                        ToneEvolution.previous_tone_id.in_(current_ids),
                    )
                ).count()
            return {"report_id": report_id, "status": "READY", "tones": tones_count, "evolutions": evolutions_count}

        try:
            repo.mark_tone_extracting(report)

            if report.company_id is None:
                repo.replace_tone_records(rid, [])
                repo.replace_tone_evolution(uuid.UUID("00000000-0000-0000-0000-000000000000"), rid, None, [])
                repo.mark_tone_extracted(report)
                log.info("tone_extraction.no_company", report_id=report_id)
                return {"report_id": report_id, "status": "READY", "tones": 0, "evolutions": 0}

            # 1. Load candidate chunks for tone extraction
            chunks = repo.get_extraction_chunks(rid, TONE_CANDIDATE_SECTIONS)
            inputs = []
            for ch in chunks:
                normalized_section_name = None
                if ch.chunk_metadata and isinstance(ch.chunk_metadata, dict):
                    normalized_section_name = ch.chunk_metadata.get("normalized_section_name")
                inputs.append(
                    ToneChunkInput(
                        chunk_id=str(ch.id),
                        text=ch.chunk_text,
                        normalized_section_name=normalized_section_name,
                        fiscal_year=report.year,
                        fiscal_quarter=report.quarter,
                    )
                )

            # 2. Extract tone
            result = HybridToneAnalyzer().analyze(report.company_id, inputs)

            # 3. Store tone records
            tone_rows = [
                {
                    "company_id": r.company_id,
                    "source_chunk_id": r.source_chunk_id,
                    "source_type": r.source_type,
                    "sentiment": r.sentiment.value,
                    "confidence_level": r.confidence_level.value,
                    "hedging_score": r.hedging_score,
                    "positive_score": r.positive_score,
                    "negative_score": r.negative_score,
                    "confidence_score": r.confidence_score,
                    "extraction_method": r.extraction_method,
                    "source_text": r.source_text,
                }
                for r in result.tone_records
            ]
            tones_count = repo.replace_tone_records(rid, tone_rows)

            # 4. Fetch prior period's tone records for evolution
            prior_report = repo.get_prior_report(report)
            prior_report_id = prior_report.id if prior_report else None

            # Need to reload saved current records to have IDs assigned
            current_saved = repo.get_report_tone(rid)
            prior_saved = repo.get_report_tone(prior_report_id) if prior_report_id else []

            # 5. Generate PoP evolution
            evolutions = ToneEvolutionService().generate_evolution(
                report.company_id,
                current_saved,
                prior_saved,
            )

            # 6. Store evolution records
            evolution_rows = [
                {
                    "current_tone_id": e.current_tone_id,
                    "previous_tone_id": e.previous_tone_id,
                    "evolution_type": e.evolution_type.value,
                    "confidence_score": e.confidence_score,
                    "explanation": e.explanation,
                }
                for e in evolutions
            ]

            ev_count = repo.replace_tone_evolution(
                report.company_id,
                rid,
                prior_report_id,
                evolution_rows,
            )

            repo.mark_tone_extracted(report)

            log.info(
                "tone_extraction.task_success",
                report_id=report_id,
                tones=tones_count,
                evolutions=ev_count,
                **result.stats.as_dict(),
            )
            return {
                "report_id": report_id,
                "status": "READY",
                "tones": tones_count,
                "evolutions": ev_count,
                **result.stats.as_dict(),
            }

        except Exception as exc:  # noqa: BLE001
            log.error("tone_extraction.task_failure", report_id=report_id, error=str(exc))
            session.rollback()
            failed = repo.get_report(rid)
            if failed is not None:
                repo.mark_failed(failed, message=f"{type(exc).__name__}: {exc}")
            return {"report_id": report_id, "status": "FAILED", "error": str(exc)}


