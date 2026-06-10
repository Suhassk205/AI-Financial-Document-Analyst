"""Integration tests for the Celery processing task against a real DB.

Exercises the success path (PDF → pages → PROCESSED) and the failure path
(missing file → FAILED with a recorded reason).
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.ingestion.storage import get_storage
from app.models.enums import ReportStatus, ReportType
from app.models.report import Report
from app.models.report_page import ReportPage
from app.tasks.ingestion import process_report


def _insert_report(session: Session, storage_path: str) -> uuid.UUID:
    report = Report(
        report_type=ReportType.TEN_Q,
        year=2026,
        quarter=1,
        original_filename="acme.pdf",
        storage_path=storage_path,
        status=ReportStatus.UPLOADED,
    )
    session.add(report)
    session.commit()
    return report.id


@pytest.mark.integration
def test_process_report_success(sync_session: Session, tiny_pdf_bytes: bytes) -> None:
    storage = get_storage()
    storage_path = storage.save(tiny_pdf_bytes, extension=".pdf")

    report_id = _insert_report(sync_session, storage_path)
    result = process_report(str(report_id))

    assert result["status"] == "PROCESSED"
    refreshed = sync_session.get(Report, report_id)
    sync_session.refresh(refreshed)
    assert refreshed.status == ReportStatus.PROCESSED
    assert refreshed.total_pages == 2

    pages = (
        sync_session.query(ReportPage)
        .filter(ReportPage.report_id == report_id)
        .order_by(ReportPage.page_number)
        .all()
    )
    assert [p.page_number for p in pages] == [1, 2]
    assert pages[0].page_text.strip() != ""


@pytest.mark.integration
def test_process_report_missing_file_marks_failed(sync_session: Session) -> None:
    # Point at a storage path that doesn't exist on disk.
    report_id = _insert_report(sync_session, "reports/2026/06/does_not_exist.pdf")
    result = process_report(str(report_id))

    assert result["status"] == "FAILED"
    refreshed = sync_session.get(Report, report_id)
    sync_session.refresh(refreshed)
    assert refreshed.status == ReportStatus.FAILED
    assert refreshed.error_message is not None
    assert refreshed.total_pages is None


@pytest.mark.integration
def test_process_report_unknown_id_is_noop(sync_session: Session) -> None:
    result = process_report(str(uuid.uuid4()))
    assert result["status"] == "MISSING"
