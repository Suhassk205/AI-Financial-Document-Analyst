"""Integration tests for the reports API + end-to-end processing."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.tasks.ingestion import process_report

PREFIX = settings.api_v1_prefix


@pytest.mark.integration
async def test_upload_creates_report_then_full_pipeline(
    api_client: AsyncClient, tiny_pdf_bytes: bytes
) -> None:
    # --- upload ---
    resp = await api_client.post(
        f"{PREFIX}/reports/upload",
        files={"file": ("acme_10q.pdf", tiny_pdf_bytes, "application/pdf")},
        data={"report_type": "10-Q", "year": "2026", "quarter": "1", "ticker": "ACME"},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "UPLOADED"
    report_id = body["report_id"]

    # --- detail before processing ---
    detail = (await api_client.get(f"{PREFIX}/reports/{report_id}")).json()
    assert detail["status"] == "UPLOADED"
    assert detail["original_filename"] == "acme_10q.pdf"

    # --- run the worker task directly (delay was stubbed in the fixture) ---
    result = process_report(report_id)
    assert result["status"] == "PROCESSED"
    assert result["total_pages"] == 2

    # --- detail after processing ---
    detail = (await api_client.get(f"{PREFIX}/reports/{report_id}")).json()
    assert detail["status"] == "PROCESSED"
    assert detail["total_pages"] == 2
    assert detail["processing_completed_at"] is not None

    # --- pages ---
    pages = (await api_client.get(f"{PREFIX}/reports/{report_id}/pages?limit=10")).json()
    assert pages["total_pages"] == 2
    assert pages["items"][0]["page_number"] == 1
    assert "Revenue" in pages["items"][0]["page_text"]


@pytest.mark.integration
async def test_list_reports(api_client: AsyncClient, tiny_pdf_bytes: bytes) -> None:
    for i in range(3):
        await api_client.post(
            f"{PREFIX}/reports/upload",
            files={"file": (f"f{i}.pdf", tiny_pdf_bytes, "application/pdf")},
            data={"report_type": "10-K", "year": "2025"},
        )
    listing = (await api_client.get(f"{PREFIX}/reports?limit=2&offset=0")).json()
    assert listing["total"] == 3
    assert len(listing["items"]) == 2
    assert listing["limit"] == 2


@pytest.mark.integration
async def test_get_unknown_report_returns_404(api_client: AsyncClient) -> None:
    resp = await api_client.get(f"{PREFIX}/reports/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.integration
async def test_upload_non_pdf_is_rejected(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        f"{PREFIX}/reports/upload",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
        data={"report_type": "OTHER", "year": "2026"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] in {"UNSUPPORTED_FILE_TYPE", "VALIDATION_ERROR"}


@pytest.mark.integration
async def test_upload_fake_pdf_bytes_rejected_by_magic_check(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        f"{PREFIX}/reports/upload",
        files={"file": ("fake.pdf", b"this is not really a pdf", "application/pdf")},
        data={"report_type": "OTHER", "year": "2026"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"
