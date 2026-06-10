"""Unit tests for the PyMuPDF parser — real parse + failure cases.

Skips automatically if PyMuPDF is not installed in the environment.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.exceptions import PdfParseError
from app.ingestion.pdf_parser import parse_pdf

fitz = pytest.importorskip("fitz", reason="PyMuPDF not installed")


def _make_pdf(path: Path, pages_text: list[str]) -> None:
    doc = fitz.open()
    for text in pages_text:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    doc.set_metadata({"title": "Test Filing", "author": "Unit Test"})
    doc.save(str(path))
    doc.close()


@pytest.mark.unit
def test_parses_multi_page_pdf(tmp_path: Path) -> None:
    pdf = tmp_path / "doc.pdf"
    _make_pdf(pdf, ["Page one revenue", "Page two risks", "Page three outlook"])

    parsed = parse_pdf(pdf)

    assert parsed.total_pages == 3
    assert [p.page_number for p in parsed.pages] == [1, 2, 3]
    assert "revenue" in parsed.pages[0].text
    assert parsed.metadata.get("title") == "Test Filing"


@pytest.mark.unit
def test_to_dict_shape(tmp_path: Path) -> None:
    pdf = tmp_path / "doc.pdf"
    _make_pdf(pdf, ["only page"])
    out = parse_pdf(pdf).to_dict()
    assert out["total_pages"] == 1
    assert out["pages"][0]["page_number"] == 1
    assert "metadata" in out


@pytest.mark.unit
def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(PdfParseError):
        parse_pdf(tmp_path / "does_not_exist.pdf")


@pytest.mark.unit
def test_corrupt_file_raises(tmp_path: Path) -> None:
    bad = tmp_path / "corrupt.pdf"
    bad.write_bytes(b"%PDF-1.7 but totally broken content")
    with pytest.raises(PdfParseError):
        parse_pdf(bad)
