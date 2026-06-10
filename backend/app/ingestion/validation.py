"""Upload validation (Phase 1A).

Pure functions that validate an upload's filename, content type, and size against
configured limits. They raise domain errors (app.core.exceptions) which the API
layer maps to HTTP responses — no HTTP concerns leak in here.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from app.core.config import settings
from app.core.exceptions import (
    EmptyFileError,
    FileTooLargeError,
    UnsupportedFileTypeError,
)

# A genuine PDF starts with "%PDF-". Cheap magic-byte sniff to reject mislabeled files.
_PDF_MAGIC = b"%PDF-"


def validate_extension(filename: str | None) -> str:
    """Return the lowercased extension if allowed, else raise."""
    if not filename:
        raise UnsupportedFileTypeError("Missing filename")
    ext = PurePosixPath(filename).suffix.lower()
    if ext not in settings.allowed_upload_extensions_set:
        raise UnsupportedFileTypeError(
            "Unsupported file extension",
            details={"extension": ext, "allowed": sorted(settings.allowed_upload_extensions_set)},
        )
    return ext


def validate_content_type(content_type: str | None) -> None:
    if content_type is None:
        return  # some clients omit it; magic-byte check is the real guard
    if content_type.lower() not in settings.allowed_upload_content_types_set:
        raise UnsupportedFileTypeError(
            "Unsupported content type",
            details={
                "content_type": content_type,
                "allowed": sorted(settings.allowed_upload_content_types_set),
            },
        )


def validate_size(num_bytes: int) -> None:
    if num_bytes <= 0:
        raise EmptyFileError("Uploaded file is empty")
    if num_bytes > settings.max_upload_size_bytes:
        raise FileTooLargeError(
            "File exceeds maximum allowed size",
            details={"size_bytes": num_bytes, "max_bytes": settings.max_upload_size_bytes},
        )


def validate_magic_bytes(data: bytes) -> None:
    """Reject files that are not actually PDFs regardless of extension/MIME."""
    if not data.startswith(_PDF_MAGIC):
        raise UnsupportedFileTypeError("File content is not a valid PDF")


def validate_upload(*, filename: str | None, content_type: str | None, data: bytes) -> str:
    """Run all upload checks. Returns the validated extension."""
    ext = validate_extension(filename)
    validate_content_type(content_type)
    validate_size(len(data))
    validate_magic_bytes(data)
    return ext
