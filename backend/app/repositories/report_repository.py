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
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.enums import ReportStatus, ReportType
from app.models.report import Report
from app.models.report_page import ReportPage


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


class SyncReportRepository:
    """Sync repository for the Celery worker's processing task."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_report(self, report_id: uuid.UUID) -> Report | None:
        return self.session.get(Report, report_id)

    def mark_processing(self, report: Report) -> None:
        report.status = ReportStatus.PROCESSING
        report.processing_started_at = datetime.now(timezone.utc)
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
        report.processing_completed_at = datetime.now(timezone.utc)
        self.session.commit()

    def mark_failed(self, report: Report, *, message: str) -> None:
        report.status = ReportStatus.FAILED
        report.error_message = message[:2000]
        report.processing_completed_at = datetime.now(timezone.utc)
        self.session.commit()
