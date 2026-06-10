"""Unit tests for upload validation — success AND failure paths."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.core.exceptions import (
    EmptyFileError,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from app.ingestion.validation import (
    validate_content_type,
    validate_extension,
    validate_magic_bytes,
    validate_size,
    validate_upload,
)

PDF_BYTES = b"%PDF-1.7\n%%EOF\n"


@pytest.mark.unit
def test_valid_pdf_upload_passes() -> None:
    ext = validate_upload(
        filename="acme_10q.pdf", content_type="application/pdf", data=PDF_BYTES
    )
    assert ext == ".pdf"


@pytest.mark.unit
def test_rejects_non_pdf_extension() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        validate_extension("report.docx")


@pytest.mark.unit
def test_rejects_missing_filename() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        validate_extension(None)


@pytest.mark.unit
def test_rejects_bad_content_type() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        validate_content_type("text/html")


@pytest.mark.unit
def test_missing_content_type_is_allowed() -> None:
    # Magic-byte check is the real guard; a missing MIME must not hard-fail.
    validate_content_type(None)


@pytest.mark.unit
def test_rejects_empty_file() -> None:
    with pytest.raises(EmptyFileError):
        validate_size(0)


@pytest.mark.unit
def test_rejects_oversized_file() -> None:
    with pytest.raises(FileTooLargeError):
        validate_size(settings.max_upload_size_bytes + 1)


@pytest.mark.unit
def test_rejects_file_with_wrong_magic_bytes() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        validate_magic_bytes(b"PK\x03\x04 this is actually a zip/docx")


@pytest.mark.unit
def test_upload_with_pdf_extension_but_non_pdf_content_is_rejected() -> None:
    # A file renamed to .pdf but whose bytes are not a PDF must be rejected.
    with pytest.raises(UnsupportedFileTypeError):
        validate_upload(filename="fake.pdf", content_type=None, data=b"not a pdf at all")
