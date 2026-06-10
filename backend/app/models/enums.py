"""Enumerations shared by ORM models and schemas (Phase 1A)."""

from __future__ import annotations

from enum import Enum


class ReportType(str, Enum):
    """Supported financial document types. Phase 1A accepts PDFs of these kinds."""

    TEN_K = "10-K"
    TEN_Q = "10-Q"
    TRANSCRIPT = "TRANSCRIPT"
    OTHER = "OTHER"


class ReportStatus(str, Enum):
    """Lifecycle of a report through the ingestion pipeline."""

    UPLOADED = "UPLOADED"        # file stored, record created, task queued
    PROCESSING = "PROCESSING"    # worker is parsing the PDF
    PROCESSED = "PROCESSED"      # pages extracted and persisted
    FAILED = "FAILED"            # processing failed (see error_message / logs)
