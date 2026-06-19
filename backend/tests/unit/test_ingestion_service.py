"""Unit tests for ReportIngestionService — orchestration without a real DB.

Uses in-memory fakes for the session, repository, and storage, and stubs the
Celery task so no broker is required. Covers the failure path (invalid upload)
and the success path (record created + task enqueued).
"""

from __future__ import annotations

import uuid

import pytest

from app.core.exceptions import UnsupportedFileTypeError
from app.ingestion.services.report_ingestion_service import ReportIngestionService
from app.models.enums import ReportStatus, ReportType

PDF_BYTES = b"%PDF-1.7\nfake body\n%%EOF\n"


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class FakeCompany:
    def __init__(self, **kw) -> None:
        self.id = uuid.uuid4()
        self.__dict__.update(kw)


class FakeReport:
    def __init__(self, **kw) -> None:
        self.id = uuid.uuid4()
        self.status = ReportStatus.UPLOADED
        self.__dict__.update(kw)


class FakeRepo:
    def __init__(self) -> None:
        self.created_report: FakeReport | None = None
        self.company_calls = 0

    async def get_or_create_company(self, **kw) -> FakeCompany:
        self.company_calls += 1
        self.company_kwargs = kw
        return FakeCompany(**kw)

    async def create_report(self, **kw) -> FakeReport:
        self.created_report = FakeReport(**kw)
        return self.created_report


class FakeStorage:
    def __init__(self) -> None:
        self.saved: bytes | None = None

    def save(self, data: bytes, *, extension: str = ".pdf") -> str:
        self.saved = data
        return f"reports/2026/06/{uuid.uuid4().hex}{extension}"


@pytest.fixture
def stub_celery(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace the real task with a recorder so no broker is needed."""
    enqueued: list[str] = []

    class _Task:
        def delay(self, report_id: str) -> None:
            enqueued.append(report_id)

    monkeypatch.setattr("app.tasks.ingestion.process_report", _Task())
    return enqueued


@pytest.mark.unit
async def test_invalid_file_type_is_rejected(stub_celery: list[str]) -> None:
    service = ReportIngestionService(FakeSession(), storage=FakeStorage(), repository=FakeRepo())
    with pytest.raises(UnsupportedFileTypeError):
        await service.ingest_upload(
            data=b"not a pdf",
            original_filename="bad.pdf",
            content_type="application/pdf",
            report_type=ReportType.TEN_Q,
            year=2026,
            quarter=1,
        )
    assert stub_celery == []  # nothing queued on failure


@pytest.mark.unit
async def test_successful_upload_creates_report_and_enqueues(stub_celery: list[str]) -> None:
    session = FakeSession()
    repo = FakeRepo()
    storage = FakeStorage()
    service = ReportIngestionService(session, storage=storage, repository=repo)

    report = await service.ingest_upload(
        data=PDF_BYTES,
        original_filename="acme_10k.pdf",
        content_type="application/pdf",
        report_type=ReportType.TEN_K,
        year=2025,
        quarter=None,
        ticker="ACME",
        company_name="Acme Inc.",
    )

    assert report is repo.created_report
    assert repo.created_report.file_data == PDF_BYTES  # file data was passed
    assert storage.saved == PDF_BYTES          # file was stored
    assert repo.company_calls == 1             # company resolved
    assert session.commits == 1                # record committed
    assert stub_celery == [str(report.id)]     # processing enqueued


@pytest.mark.unit
async def test_upload_without_company_derives_company_from_filename(stub_celery: list[str]) -> None:
    """A company is ALWAYS attached so risk/tone (NOT NULL company_id) persist.

    When no ticker/name is supplied we fall back to a name derived from the
    uploaded filename so the report is never left company-less.
    """
    repo = FakeRepo()
    service = ReportIngestionService(FakeSession(), storage=FakeStorage(), repository=repo)
    await service.ingest_upload(
        data=PDF_BYTES,
        original_filename="anon.pdf",
        content_type="application/pdf",
        report_type=ReportType.OTHER,
        year=2026,
    )
    assert repo.company_calls == 1
    assert repo.company_kwargs["name"] == "anon"   # derived from filename stem
    assert repo.company_kwargs["ticker"] is None
    assert repo.created_report is not None
    assert repo.created_report.company_id is not None
