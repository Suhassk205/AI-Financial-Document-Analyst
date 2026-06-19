"""Report ingestion service — orchestrates the upload use-case.

Responsibilities (Phase 1A):
  1. validate the upload (type/size/magic bytes),
  2. store the raw file under a UUID name,
  3. resolve/create the company (optional),
  4. create the report record (status=UPLOADED),
  5. enqueue the async processing task.

All business logic lives here, not in the API route (docs/09 §). The service is
constructed with its collaborators (DI-friendly) so tests can substitute fakes.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.ingestion.storage import LocalStorage, get_storage
from app.ingestion.validation import validate_upload
from app.models.enums import ReportType
from app.models.report import Report
from app.repositories.report_repository import ReportRepository

log = get_logger(__name__)


class ReportIngestionService:
    def __init__(
        self,
        session: AsyncSession,
        storage: LocalStorage | None = None,
        repository: ReportRepository | None = None,
    ) -> None:
        self.session = session
        self.storage = storage or get_storage()
        self.repo = repository or ReportRepository(session)

    async def ingest_upload(
        self,
        *,
        data: bytes,
        original_filename: str | None,
        content_type: str | None,
        report_type: ReportType,
        year: int,
        quarter: int | None = None,
        ticker: str | None = None,
        company_name: str | None = None,
    ) -> Report:
        """Validate, store, persist a report record, and enqueue processing."""
        log.info(
            "upload.start",
            filename=original_filename,
            content_type=content_type,
            report_type=report_type.value,
            size_bytes=len(data),
        )

        # 1. Validate (raises domain errors mapped to HTTP by the API layer).
        ext = validate_upload(
            filename=original_filename, content_type=content_type, data=data
        )

        if quarter is not None and not (1 <= quarter <= 4):
            raise ValidationError("quarter must be between 1 and 4", details={"quarter": quarter})

        # 2. Store the raw bytes under a fresh UUID name.
        storage_path = self.storage.save(data, extension=ext)

        # 3. Resolve/create the company. A company is ALWAYS attached: the
        #    company-scoped extractions (risk factors + management tone) have a
        #    NOT NULL company_id, so a report with no company would silently
        #    produce zero tone records and fail risk extraction. When the user
        #    does not supply a ticker/name we derive a stable fallback name from
        #    the uploaded filename so those stages still persist results.
        resolved_name = (company_name or ticker or "").strip()
        if not resolved_name:
            stem = (original_filename or "").rsplit("/", 1)[-1]
            if "." in stem:
                stem = stem.rsplit(".", 1)[0]
            resolved_name = stem.strip() or "Unknown Company"
        company = await self.repo.get_or_create_company(
            name=resolved_name,
            ticker=ticker,
        )
        company_id: uuid.UUID | None = company.id

        # 4. Create the report record.
        report = await self.repo.create_report(
            company_id=company_id,
            report_type=report_type,
            year=year,
            quarter=quarter,
            original_filename=original_filename or f"upload{ext}",
            storage_path=storage_path,
            file_data=data,
        )
        await self.session.commit()

        # 5. Enqueue async processing. Imported here to avoid an import cycle
        #    (celery_app discovers tasks; tasks import db/models).
        from app.tasks.ingestion import process_report

        process_report.delay(str(report.id))

        log.info("upload.success", report_id=str(report.id), storage_path=storage_path)
        return report
