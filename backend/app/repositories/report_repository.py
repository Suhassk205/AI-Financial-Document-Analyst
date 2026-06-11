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

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.document_chunk import DocumentChunk
from app.models.enums import EmbeddingStatus, ReportStatus, ReportType
from app.models.report import Report
from app.models.report_page import ReportPage
from app.models.report_section import ReportSection


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
    ) -> Report:
        report = Report(
            company_id=company_id,
            report_type=report_type,
            year=year,
            quarter=quarter,
            original_filename=original_filename,
            storage_path=storage_path,
            status=ReportStatus.UPLOADED,
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
        report.processing_completed_at = datetime.now(UTC)
        self.session.commit()

    def mark_failed(self, report: Report, *, message: str) -> None:
        report.status = ReportStatus.FAILED
        report.error_message = message[:2000]
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
