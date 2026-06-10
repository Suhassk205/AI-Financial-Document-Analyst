"""PDF extraction engine (PyMuPDF / fitz).

Phase 1A scope: extract raw per-page text, page numbers, and document metadata.
NO section detection, NO chunking, NO OCR. Scanned/image-only PDFs are out of
scope — pages with no extractable text are returned as empty strings (and the
caller may surface this as a quality signal), but OCR is a future enhancement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.core.exceptions import PdfParseError
from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class ParsedPage:
    page_number: int  # 1-based
    text: str


@dataclass(frozen=True)
class ParsedDocument:
    total_pages: int
    pages: list[ParsedPage]
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "total_pages": self.total_pages,
            "metadata": self.metadata,
            "pages": [{"page_number": p.page_number, "text": p.text} for p in self.pages],
        }


def parse_pdf(path: str | Path) -> ParsedDocument:
    """Parse a PDF file into structured per-page text + metadata.

    Raises:
        PdfParseError: if the file is missing, not a PDF, or cannot be opened.
    """
    # Imported lazily so the rest of the app (and unit tests that don't parse)
    # don't require PyMuPDF to be installed.
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise PdfParseError("PyMuPDF (pymupdf) is not installed") from exc

    path = Path(path)
    if not path.exists():
        raise PdfParseError("File not found", details={"path": str(path)})

    try:
        doc = fitz.open(path)
    except Exception as exc:  # noqa: BLE001 - normalize any fitz error
        raise PdfParseError("Failed to open PDF", details={"reason": str(exc)}) from exc

    try:
        if doc.page_count == 0:
            raise PdfParseError("PDF has no pages")

        pages: list[ParsedPage] = []
        for index in range(doc.page_count):
            page = doc.load_page(index)
            text = page.get_text("text") or ""
            pages.append(ParsedPage(page_number=index + 1, text=text))

        raw_meta = doc.metadata or {}
        metadata = {k: str(v) for k, v in raw_meta.items() if v}
        total = doc.page_count
    finally:
        doc.close()

    log.info("pdf.parsed", total_pages=total, has_metadata=bool(metadata))
    return ParsedDocument(total_pages=total, pages=pages, metadata=metadata)
