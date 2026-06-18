"""Data-access layer for reports, companies, and pages.

Two repositories with the same domain but different execution models:
  * `ReportRepository`  — async, used by the FastAPI request path.
  * `SyncReportRepository` — sync, used by the Celery worker (see app.db.session
    for why the worker is synchronous).

All raw queries live here; services and tasks never write SQL directly
(docs/07_REPOSITORY_STRUCTURE.md §6).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.document_chunk import DocumentChunk
from app.models.enums import EmbeddingStatus, ReportStatus, ReportType
from app.models.financial_metric import FinancialMetric
from app.models.metric_comparison import MetricComparison
from app.models.financial_analytics import FinancialAnalytics
from app.models.report import Report
from app.models.report_page import ReportPage
from app.models.report_section import ReportSection
from app.models.risk_factor import RiskFactor
from app.models.risk_evolution import RiskEvolution
from app.models.management_tone import ManagementTone
from app.models.tone_evolution import ToneEvolution


class ReportRepository:
    """Async repository for the API layer."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_company(
        self,
        *,
        name: str,
        ticker: str | None,
        sector: str | None = None,
        industry: str | None = None,
    ) -> Company:
        if ticker:
            existing = await self.session.scalar(
                select(Company).where(Company.ticker == ticker)
            )
            if existing:
                return existing
        company = Company(name=name, ticker=ticker, sector=sector, industry=industry)
        self.session.add(company)
        await self.session.flush()
        return company

    async def create_report(
        self,
        *,
        company_id: uuid.UUID | None,
        report_type: ReportType,
        year: int,
        quarter: int | None,
        original_filename: str,
        storage_path: str,
        file_data: bytes | None = None,
    ) -> Report:
        report = Report(
            company_id=company_id,
            report_type=report_type,
            year=year,
            quarter=quarter,
            original_filename=original_filename,
            storage_path=storage_path,
            status=ReportStatus.UPLOADED,
            file_data=file_data,
        )
        self.session.add(report)
        await self.session.flush()
        return report

    async def get_report(self, report_id: uuid.UUID) -> Report | None:
        return await self.session.get(Report, report_id)

    async def list_reports(self, *, limit: int, offset: int) -> tuple[list[Report], int]:
        total = await self.session.scalar(select(func.count()).select_from(Report)) or 0
        rows = (
            await self.session.scalars(
                select(Report).order_by(Report.uploaded_at.desc()).limit(limit).offset(offset)
            )
        ).all()
        return list(rows), int(total)

    async def get_pages(
        self, report_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[ReportPage], int]:
        total = (
            await self.session.scalar(
                select(func.count())
                .select_from(ReportPage)
                .where(ReportPage.report_id == report_id)
            )
            or 0
        )
        rows = (
            await self.session.scalars(
                select(ReportPage)
                .where(ReportPage.report_id == report_id)
                .order_by(ReportPage.page_number.asc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return list(rows), int(total)

    async def get_sections(self, report_id: uuid.UUID) -> list[ReportSection]:
        rows = (
            await self.session.scalars(
                select(ReportSection)
                .where(ReportSection.report_id == report_id)
                .order_by(ReportSection.start_page.asc())
            )
        ).all()
        return list(rows)

    async def get_section(self, section_id: uuid.UUID) -> ReportSection | None:
        return await self.session.get(ReportSection, section_id)

    # ---- Phase 1C: chunks ----------------------------------------------------

    async def get_chunks(
        self, report_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[DocumentChunk], int]:
        total = (
            await self.session.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .where(DocumentChunk.report_id == report_id)
            )
            or 0
        )
        rows = (
            await self.session.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.report_id == report_id)
                .order_by(DocumentChunk.chunk_index.asc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        return list(rows), int(total)

    async def get_all_chunks(self, report_id: uuid.UUID) -> list[DocumentChunk]:
        rows = (
            await self.session.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.report_id == report_id)
                .order_by(DocumentChunk.chunk_index.asc())
            )
        ).all()
        return list(rows)

    async def get_chunk(self, chunk_id: uuid.UUID) -> DocumentChunk | None:
        return await self.session.get(DocumentChunk, chunk_id)

    # ---- Phase 2A: embedding status / stats (read-only, API layer) ----------

    async def get_embedding_status_counts(self, report_id: uuid.UUID) -> dict[str, int]:
        """Count chunks per `embedding_status` for a report (PENDING/.../FAILED)."""
        rows = (
            await self.session.execute(
                select(DocumentChunk.embedding_status, func.count())
                .where(DocumentChunk.report_id == report_id)
                .group_by(DocumentChunk.embedding_status)
            )
        ).all()
        return {str(status): int(count) for status, count in rows}

    async def count_chunks_async(self, report_id: uuid.UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .where(DocumentChunk.report_id == report_id)
            )
            or 0
        )

    async def count_embedded_async(self, report_id: uuid.UUID) -> int:
        """Chunks with a non-null embedding (the authoritative 'embedded' count)."""
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .where(
                    DocumentChunk.report_id == report_id,
                    DocumentChunk.embedding.is_not(None),
                )
            )
            or 0
        )

    # ---- Phase 3A: financial metrics (read-only, API layer) -----------------

    async def get_metrics(
        self, report_id: uuid.UUID, *, category: str | None = None
    ) -> list[FinancialMetric]:
        stmt = select(FinancialMetric).where(FinancialMetric.report_id == report_id)
        if category is not None:
            stmt = stmt.where(FinancialMetric.metric_category == category)
        rows = (
            await self.session.scalars(
                stmt.order_by(
                    FinancialMetric.metric_category.asc(),
                    FinancialMetric.normalized_metric_name.asc(),
                )
            )
        ).all()
        return list(rows)

    async def get_metric(self, metric_id: uuid.UUID) -> FinancialMetric | None:
        return await self.session.get(FinancialMetric, metric_id)

    # ---- Phase 3B: comparisons (read-only, API layer) -----------------------

    async def get_company(self, company_id: uuid.UUID) -> Company | None:
        return await self.session.get(Company, company_id)

    async def get_comparisons_by_report(
        self, report_id: uuid.UUID
    ) -> list[MetricComparison]:
        stmt = (
            select(MetricComparison)
            .join(FinancialMetric, MetricComparison.metric_id == FinancialMetric.id)
            .where(FinancialMetric.report_id == report_id)
            .order_by(MetricComparison.metric_name.asc(), MetricComparison.comparison_type.asc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def get_comparisons_by_company(
        self, company_id: uuid.UUID, *, comparison_type: str | None = None
    ) -> list[MetricComparison]:
        stmt = select(MetricComparison).where(MetricComparison.company_id == company_id)
        if comparison_type is not None:
            stmt = stmt.where(MetricComparison.comparison_type == comparison_type)
        return list(
            (
                await self.session.scalars(
                    stmt.order_by(
                        MetricComparison.metric_name.asc(),
                        MetricComparison.comparison_type.asc(),
                    )
                )
            ).all()
        )

    async def get_comparisons_by_company_metric(
        self, company_id: uuid.UUID, metric_name: str
    ) -> list[MetricComparison]:
        stmt = (
            select(MetricComparison)
            .where(
                MetricComparison.company_id == company_id,
                MetricComparison.metric_name == metric_name,
            )
            .order_by(MetricComparison.comparison_type.asc())
        )
        return list((await self.session.scalars(stmt)).all())

    # ---- Phase 3C: financial analytics -------------------------------------

    async def get_analytics_by_report(
        self, report_id: uuid.UUID
    ) -> list[FinancialAnalytics]:
        stmt = (
            select(FinancialAnalytics)
            .where(FinancialAnalytics.report_id == report_id)
            .order_by(FinancialAnalytics.created_at.asc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def get_analytics_by_company(
        self, company_id: uuid.UUID, *, signal_type: str | None = None
    ) -> list[FinancialAnalytics]:
        stmt = select(FinancialAnalytics).where(FinancialAnalytics.company_id == company_id)
        if signal_type is not None:
            stmt = stmt.where(FinancialAnalytics.signal_type == signal_type)
        stmt = stmt.order_by(FinancialAnalytics.created_at.asc())
        return list((await self.session.scalars(stmt)).all())

    async def get_analytics_by_company_signals(
        self, company_id: uuid.UUID
    ) -> list[FinancialAnalytics]:
        # Filter out ratios
        stmt = (
            select(FinancialAnalytics)
            .where(
                FinancialAnalytics.company_id == company_id,
                ~FinancialAnalytics.signal_code.in_([
                    "GROSS_MARGIN", "OPERATING_MARGIN", "NET_MARGIN", "DEBT_TO_REVENUE", "CASH_FLOW_MARGIN"
                ])
            )
            .order_by(FinancialAnalytics.created_at.asc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def get_analytics_by_company_ratios(
        self, company_id: uuid.UUID
    ) -> list[FinancialAnalytics]:
        # Filter for ratios only
        stmt = (
            select(FinancialAnalytics)
            .where(
                FinancialAnalytics.company_id == company_id,
                FinancialAnalytics.signal_code.in_([
                    "GROSS_MARGIN", "OPERATING_MARGIN", "NET_MARGIN", "DEBT_TO_REVENUE", "CASH_FLOW_MARGIN"
                ])
            )
            .order_by(FinancialAnalytics.created_at.asc())
        )
        return list((await self.session.scalars(stmt)).all())

    # ---- Phase 4: risk factors & risk evolution (read-only, API layer) ------

    async def get_risks(
        self, report_id: uuid.UUID, *, category: str | None = None
    ) -> list[RiskFactor]:
        stmt = select(RiskFactor).where(RiskFactor.report_id == report_id)
        if category is not None:
            stmt = stmt.where(RiskFactor.category == category)
        rows = (
            await self.session.scalars(
                stmt.order_by(
                    RiskFactor.category.asc(),
                    RiskFactor.normalized_risk_name.asc(),
                )
            )
        ).all()
        return list(rows)

    async def get_risks_by_company(
        self,
        company_id: uuid.UUID,
        *,
        category: str | None = None,
        severity: str | None = None,
    ) -> list[RiskFactor]:
        stmt = select(RiskFactor).where(RiskFactor.company_id == company_id)
        if category is not None:
            stmt = stmt.where(RiskFactor.category == category)
        if severity is not None:
            stmt = stmt.where(RiskFactor.severity == severity)
        rows = (
            await self.session.scalars(
                stmt.order_by(
                    RiskFactor.category.asc(),
                    RiskFactor.normalized_risk_name.asc(),
                )
            )
        ).all()
        return list(rows)

    async def get_risk(self, risk_id: uuid.UUID) -> RiskFactor | None:
        return await self.session.get(RiskFactor, risk_id)

    async def get_risk_evolutions_by_report(
        self, report_id: uuid.UUID
    ) -> list[RiskEvolution]:
        risk_ids = select(RiskFactor.id).where(RiskFactor.report_id == report_id)
        stmt = (
            select(RiskEvolution)
            .where(
                or_(
                    RiskEvolution.current_risk_id.in_(risk_ids),
                    RiskEvolution.previous_risk_id.in_(risk_ids),
                )
            )
            .order_by(RiskEvolution.evolution_type.asc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def get_risk_evolutions_by_company(
        self, company_id: uuid.UUID, *, evolution_type: str | None = None
    ) -> list[RiskEvolution]:
        stmt = select(RiskEvolution).where(RiskEvolution.company_id == company_id)
        if evolution_type is not None:
            stmt = stmt.where(RiskEvolution.evolution_type == evolution_type)
        stmt = stmt.order_by(RiskEvolution.created_at.asc())
        return list((await self.session.scalars(stmt)).all())

    async def get_tone_by_report(self, report_id: uuid.UUID) -> list[ManagementTone]:
        stmt = select(ManagementTone).where(ManagementTone.report_id == report_id).order_by(ManagementTone.source_type.asc())
        return list((await self.session.scalars(stmt)).all())

    async def get_tone_by_id(self, tone_id: uuid.UUID) -> ManagementTone | None:
        return await self.session.get(ManagementTone, tone_id)

    async def get_tone_by_company(self, company_id: uuid.UUID) -> list[ManagementTone]:
        stmt = (
            select(ManagementTone)
            .join(Report, ManagementTone.report_id == Report.id)
            .where(Report.company_id == company_id)
            .order_by(Report.year.asc(), Report.quarter.asc(), ManagementTone.source_type.asc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def get_tone_evolutions_by_company(self, company_id: uuid.UUID) -> list[ToneEvolution]:
        stmt = select(ToneEvolution).where(ToneEvolution.company_id == company_id).order_by(ToneEvolution.created_at.asc())
        return list((await self.session.scalars(stmt)).all())


class SyncReportRepository:
    """Sync repository for the Celery worker's processing task."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_report(self, report_id: uuid.UUID) -> Report | None:
        return self.session.get(Report, report_id)

    def mark_processing(self, report: Report) -> None:
        report.status = ReportStatus.PROCESSING
        report.processing_started_at = datetime.now(UTC)
        report.error_message = None
        report.failed_stage = None
        report.completed_stage = None
        report.retry_count = 0
        self.session.commit()

    def replace_pages(self, report_id: uuid.UUID, pages: list[tuple[int, str]]) -> int:
        """Delete any existing pages for the report and insert the new set.

        Idempotent: re-processing a report rebuilds its pages cleanly.
        """
        self.session.query(ReportPage).filter(ReportPage.report_id == report_id).delete()
        self.session.add_all(
            [ReportPage(report_id=report_id, page_number=n, page_text=t) for n, t in pages]
        )
        self.session.commit()
        return len(pages)

    def mark_processed(self, report: Report, *, total_pages: int) -> None:
        report.status = ReportStatus.PROCESSED
        report.total_pages = total_pages
        report.completed_stage = "PROCESSED"
        report.processing_completed_at = datetime.now(UTC)
        self.session.commit()

    def mark_failed(self, report: Report, *, message: str, failed_stage: str | None = None) -> None:
        report.status = ReportStatus.FAILED
        report.error_message = message[:2000]
        if failed_stage is not None:
            report.failed_stage = failed_stage
        report.processing_completed_at = datetime.now(UTC)
        self.session.commit()

    # ---- Phase 1B: section detection ----------------------------------------

    def get_pages_ordered(self, report_id: uuid.UUID) -> list[tuple[int, str]]:
        """Return (page_number, page_text) for a report, ordered by page."""
        rows = (
            self.session.query(ReportPage.page_number, ReportPage.page_text)
            .filter(ReportPage.report_id == report_id)
            .order_by(ReportPage.page_number.asc())
            .all()
        )
        return [(n, t) for n, t in rows]

    def mark_sectioning(self, report: Report) -> None:
        report.status = ReportStatus.SECTIONING
        report.error_message = None
        self.session.commit()

    def replace_sections(self, report_id: uuid.UUID, sections: list[dict]) -> int:
        """Delete existing sections for the report and insert the new set.

        Idempotent: re-running detection rebuilds sections cleanly. Each item is a
        dict with keys: section_name, normalized_section_name, start_page,
        end_page, content, confidence_score.
        """
        self.session.query(ReportSection).filter(
            ReportSection.report_id == report_id
        ).delete()
        self.session.add_all(
            [ReportSection(report_id=report_id, **s) for s in sections]
        )
        self.session.commit()
        return len(sections)

    def mark_sectioned(self, report: Report) -> None:
        report.status = ReportStatus.SECTIONED
        report.completed_stage = "SECTIONED"
        report.processing_completed_at = datetime.now(UTC)
        self.session.commit()

    # ---- Phase 1C: chunk generation -----------------------------------------

    def get_company(self, company_id: uuid.UUID | None) -> Company | None:
        if company_id is None:
            return None
        return self.session.get(Company, company_id)

    def get_sections_ordered(self, report_id: uuid.UUID) -> list[ReportSection]:
        return list(
            self.session.query(ReportSection)
            .filter(ReportSection.report_id == report_id)
            .order_by(ReportSection.start_page.asc())
            .all()
        )

    def mark_chunking(self, report: Report) -> None:
        report.status = ReportStatus.CHUNKING
        report.error_message = None
        self.session.commit()

    def replace_chunks(self, report_id: uuid.UUID, chunks: list[dict]) -> int:
        """Delete existing chunks for the report and insert the new set.

        Idempotent. Each item is a dict with keys: section_id, chunk_index,
        chunk_text, token_count, start_page, end_page, chunk_metadata.
        """
        self.session.query(DocumentChunk).filter(
            DocumentChunk.report_id == report_id
        ).delete()
        self.session.add_all(
            [DocumentChunk(report_id=report_id, **c) for c in chunks]
        )
        self.session.commit()
        return len(chunks)

    def mark_chunked(self, report: Report) -> None:
        report.status = ReportStatus.CHUNKED
        report.completed_stage = "CHUNKED"
        report.processing_completed_at = datetime.now(UTC)
        self.session.commit()

    # ---- Phase 2A: embedding generation -------------------------------------

    def get_chunks_for_embedding(
        self, report_id: uuid.UUID, *, include_completed: bool = False
    ) -> list[DocumentChunk]:
        """Chunks that still need an embedding (or all, when re-embedding).

        Default: chunks without a stored vector (NULL embedding) — i.e. PENDING,
        FAILED, or interrupted PROCESSING. This is what makes the run idempotent:
        already-COMPLETED chunks are skipped. `include_completed=True` (force)
        returns every chunk for a full re-embed.
        """
        query = self.session.query(DocumentChunk).filter(
            DocumentChunk.report_id == report_id
        )
        if not include_completed:
            query = query.filter(DocumentChunk.embedding.is_(None))
        return list(query.order_by(DocumentChunk.chunk_index.asc()).all())

    def count_chunks(self, report_id: uuid.UUID) -> int:
        return int(
            self.session.query(func.count(DocumentChunk.id))
            .filter(DocumentChunk.report_id == report_id)
            .scalar()
            or 0
        )

    def count_missing_embeddings(self, report_id: uuid.UUID) -> int:
        """Chunks still lacking a stored vector — 0 means the report is fully embedded."""
        return int(
            self.session.query(func.count(DocumentChunk.id))
            .filter(
                DocumentChunk.report_id == report_id,
                DocumentChunk.embedding.is_(None),
            )
            .scalar()
            or 0
        )

    def mark_embedding(self, report: Report) -> None:
        report.status = ReportStatus.EMBEDDING
        report.error_message = None
        self.session.commit()

    def mark_embedded(self, report: Report) -> None:
        report.status = ReportStatus.EMBEDDED
        report.completed_stage = "EMBEDDED"
        report.processing_completed_at = datetime.now(UTC)
        self.session.commit()

    def set_embedding_status(
        self, chunks: list[DocumentChunk], status: EmbeddingStatus
    ) -> None:
        """Set embedding_status on chunks in-memory (caller commits)."""
        for chunk in chunks:
            chunk.embedding_status = status.value

    def apply_embedding(
        self, chunk: DocumentChunk, *, embedding: list[float], model: str
    ) -> None:
        """Attach a validated vector to a chunk and mark it COMPLETED (no commit)."""
        chunk.embedding = embedding
        chunk.embedding_model = model
        chunk.embedding_status = EmbeddingStatus.COMPLETED.value
        chunk.embedding_generated_at = datetime.now(UTC)

    def commit(self) -> None:
        self.session.commit()

    # ---- Phase 3A: financial metric extraction ------------------------------

    def get_extraction_chunks(
        self, report_id: uuid.UUID, sections: tuple[str, ...]
    ) -> list[DocumentChunk]:
        """Candidate chunks for metric extraction: those in financial sections."""
        query = self.session.query(DocumentChunk).filter(
            DocumentChunk.report_id == report_id
        )
        if sections:
            conds = [
                DocumentChunk.chunk_metadata.contains({"normalized_section_name": s})
                for s in sections
            ]
            query = query.filter(or_(*conds))
        return list(query.order_by(DocumentChunk.chunk_index.asc()).all())

    def count_chunks_for_report(self, report_id: uuid.UUID) -> int:
        return int(
            self.session.query(func.count(DocumentChunk.id))
            .filter(DocumentChunk.report_id == report_id)
            .scalar()
            or 0
        )

    def mark_extracting(self, report: Report) -> None:
        report.status = ReportStatus.METRICS_EXTRACTING
        report.error_message = None
        self.session.commit()

    def replace_metrics(self, report_id: uuid.UUID, metrics: list[dict]) -> int:
        """Delete existing metrics for the report and insert the new set (idempotent)."""
        self.session.query(FinancialMetric).filter(
            FinancialMetric.report_id == report_id
        ).delete()
        self.session.add_all(
            [FinancialMetric(report_id=report_id, **m) for m in metrics]
        )
        self.session.commit()
        return len(metrics)

    def mark_extracted(self, report: Report) -> None:
        report.status = ReportStatus.METRICS_READY
        report.completed_stage = "METRICS_READY"
        report.processing_completed_at = datetime.now(UTC)
        self.session.commit()

    # ---- Phase 3B: comparison generation ------------------------------------

    def get_company_metrics(self, company_id: uuid.UUID) -> list[FinancialMetric]:
        """All financial metrics for a company across its reports."""
        return list(
            self.session.query(FinancialMetric)
            .join(Report, FinancialMetric.report_id == Report.id)
            .filter(Report.company_id == company_id)
            .all()
        )

    def get_report_metrics(self, report_id: uuid.UUID) -> list[FinancialMetric]:
        return list(
            self.session.query(FinancialMetric)
            .filter(FinancialMetric.report_id == report_id)
            .all()
        )

    def mark_comparing(self, report: Report) -> None:
        report.status = ReportStatus.COMPARING
        report.error_message = None
        self.session.commit()

    def replace_report_comparisons(self, report_id: uuid.UUID, rows: list[dict]) -> int:
        """Rebuild comparisons anchored to this report's metrics (idempotent)."""
        metric_ids = select(FinancialMetric.id).where(FinancialMetric.report_id == report_id)
        self.session.query(MetricComparison).filter(
            MetricComparison.metric_id.in_(metric_ids)
        ).delete(synchronize_session=False)
        self.session.add_all([MetricComparison(**r) for r in rows])
        self.session.commit()
        return len(rows)

    def mark_compared(self, report: Report) -> None:
        report.status = ReportStatus.COMPARISON_READY
        report.completed_stage = "COMPARISON_READY"
        report.processing_completed_at = datetime.now(UTC)
        self.session.commit()

    # ---- Phase 3C: financial analytics -------------------------------------

    def mark_analyzing(self, report: Report) -> None:
        report.status = ReportStatus.ANALYTICS
        report.error_message = None
        self.session.commit()

    def get_company_comparisons(self, company_id: uuid.UUID) -> list[MetricComparison]:
        return list(
            self.session.query(MetricComparison)
            .filter(MetricComparison.company_id == company_id)
            .all()
        )

    def replace_report_analytics(self, report_id: uuid.UUID, rows: list[dict]) -> int:
        """Rebuild analytics for this report (idempotent)."""
        self.session.query(FinancialAnalytics).filter(
            FinancialAnalytics.report_id == report_id
        ).delete(synchronize_session=False)
        self.session.add_all([FinancialAnalytics(**r) for r in rows])
        self.session.commit()
        return len(rows)

    def mark_analyzed(self, report: Report) -> None:
        report.status = ReportStatus.ANALYTICS_READY
        report.completed_stage = "ANALYTICS_READY"
        report.processing_completed_at = datetime.now(UTC)
        self.session.commit()

    # ---- Phase 4: risk factors & risk evolution (sync, Celery worker) --------

    def mark_risk_extracting(self, report: Report) -> None:
        report.status = ReportStatus.RISKS
        report.error_message = None
        self.session.commit()

    def replace_risks(self, report_id: uuid.UUID, risks: list[dict]) -> int:
        """Delete existing risk factors for the report and insert the new set (idempotent)."""
        self.session.query(RiskFactor).filter(
            RiskFactor.report_id == report_id
        ).delete()
        self.session.add_all(
            [RiskFactor(report_id=report_id, **r) for r in risks]
        )
        self.session.commit()
        return len(risks)

    def mark_risk_extracted(self, report: Report) -> None:
        report.status = ReportStatus.RISKS_READY
        report.completed_stage = "RISKS_READY"
        report.processing_completed_at = datetime.now(UTC)
        self.session.commit()

    def get_report_risks(self, report_id: uuid.UUID) -> list[RiskFactor]:
        return list(
            self.session.query(RiskFactor)
            .filter(RiskFactor.report_id == report_id)
            .all()
        )

    def get_company_risks(self, company_id: uuid.UUID) -> list[RiskFactor]:
        """All risk factors for a company across its reports."""
        return list(
            self.session.query(RiskFactor)
            .join(Report, RiskFactor.report_id == Report.id)
            .filter(Report.company_id == company_id)
            .all()
        )

    def get_prior_report(self, report: Report) -> Report | None:
        """Find the prior chronological report for the same company.

        Chronological order: sort by (year, quarter if quarter is not None else 4) ASC.
        Returns the report immediately preceding the given report.
        """
        if report.company_id is None:
            return None
        all_reports = (
            self.session.query(Report)
            .filter(Report.company_id == report.company_id)
            .all()
        )
        def sort_key(r: Report):
            q = r.quarter if r.quarter is not None else 4
            return (r.year, q)

        sorted_reports = sorted(all_reports, key=sort_key)
        try:
            idx = next(i for i, r in enumerate(sorted_reports) if r.id == report.id)
            if idx > 0:
                return sorted_reports[idx - 1]
        except StopIteration:
            pass
        return None

    def replace_risk_evolution(
        self,
        company_id: uuid.UUID,
        report_id: uuid.UUID,
        prior_report_id: uuid.UUID | None,
        rows: list[dict],
    ) -> int:
        """Rebuild risk evolution records for this period comparison (idempotent)."""
        current_ids = select(RiskFactor.id).where(RiskFactor.report_id == report_id)
        if prior_report_id:
            prior_ids = select(RiskFactor.id).where(RiskFactor.report_id == prior_report_id)
            self.session.query(RiskEvolution).filter(
                RiskEvolution.company_id == company_id,
                or_(
                    RiskEvolution.current_risk_id.in_(current_ids),
                    or_(
                        RiskEvolution.previous_risk_id.in_(current_ids),
                        # Handles REMOVED_RISKs (current is NULL, previous is in prior report)
                        and_(
                            RiskEvolution.previous_risk_id.in_(prior_ids),
                            RiskEvolution.current_risk_id.is_(None)
                        )
                    )
                )
            ).delete(synchronize_session=False)
        else:
            self.session.query(RiskEvolution).filter(
                RiskEvolution.company_id == company_id,
                or_(
                    RiskEvolution.current_risk_id.in_(current_ids),
                    RiskEvolution.previous_risk_id.in_(current_ids),
                )
            ).delete(synchronize_session=False)

        self.session.add_all([RiskEvolution(company_id=company_id, **r) for r in rows])
        self.session.commit()
        return len(rows)

    def replace_tone_records(self, report_id: uuid.UUID, tones: list[dict]) -> int:
        """Delete existing tone records for the report and insert the new set.

        Idempotent.
        """
        self.session.query(ManagementTone).filter(
            ManagementTone.report_id == report_id
        ).delete()
        self.session.add_all(
            [ManagementTone(report_id=report_id, **t) for t in tones]
        )
        self.session.commit()
        return len(tones)

    def mark_tone_extracting(self, report: Report) -> None:
        report.status = ReportStatus.TONE
        report.error_message = None
        self.session.commit()

    def mark_tone_extracted(self, report: Report) -> None:
        report.status = ReportStatus.READY
        report.completed_stage = "READY"
        report.processing_completed_at = datetime.now(UTC)
        self.session.commit()

    def get_report_tone(self, report_id: uuid.UUID) -> list[ManagementTone]:
        return list(
            self.session.query(ManagementTone)
            .filter(ManagementTone.report_id == report_id)
            .all()
        )

    def get_company_tone(self, company_id: uuid.UUID) -> list[ManagementTone]:
        return list(
            self.session.query(ManagementTone)
            .join(Report, ManagementTone.report_id == Report.id)
            .filter(Report.company_id == company_id)
            .all()
        )

    def replace_tone_evolution(
        self,
        company_id: uuid.UUID,
        report_id: uuid.UUID,
        prior_report_id: uuid.UUID | None,
        rows: list[dict],
    ) -> int:
        """Rebuild tone evolution records for this period comparison (idempotent)."""
        current_ids = select(ManagementTone.id).where(ManagementTone.report_id == report_id)
        if prior_report_id:
            prior_ids = select(ManagementTone.id).where(ManagementTone.report_id == prior_report_id)
            self.session.query(ToneEvolution).filter(
                ToneEvolution.company_id == company_id,
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
            ).delete(synchronize_session=False)
        else:
            self.session.query(ToneEvolution).filter(
                ToneEvolution.company_id == company_id,
                or_(
                    ToneEvolution.current_tone_id.in_(current_ids),
                    ToneEvolution.previous_tone_id.in_(current_ids),
                )
            ).delete(synchronize_session=False)

        self.session.add_all([ToneEvolution(company_id=company_id, **r) for r in rows])
        self.session.commit()
        return len(rows)
