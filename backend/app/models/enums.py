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
    """Lifecycle of a report through the ingestion + structure pipeline."""

    UPLOADED = "UPLOADED"        # file stored, record created, task queued
    PROCESSING = "PROCESSING"    # worker is parsing the PDF (Phase 1A)
    PROCESSED = "PROCESSED"      # pages extracted and persisted (Phase 1A done)
    SECTIONING = "SECTIONING"    # worker is detecting sections (Phase 1B)
    SECTIONED = "SECTIONED"      # sections detected and persisted (Phase 1B done)
    CHUNKING = "CHUNKING"        # worker is generating chunks (Phase 1C)
    CHUNKED = "CHUNKED"          # chunks generated and persisted (Phase 1C done)
    EMBEDDING = "EMBEDDING"      # worker is generating embeddings (Phase 2A)
    EMBEDDED = "EMBEDDED"        # every chunk has a valid embedding (Phase 2A done)
    FAILED = "FAILED"            # a processing step failed (see error_message / logs)


class EmbeddingStatus(str, Enum):
    """Per-chunk embedding lifecycle (Phase 2A) — operational visibility.

    Tracked on `document_chunks.embedding_status` so we can answer
    "does every chunk have a valid embedding?" and locate stragglers/failures.
    """

    PENDING = "PENDING"          # chunk exists, no embedding yet
    PROCESSING = "PROCESSING"    # embedding is being generated for this chunk
    COMPLETED = "COMPLETED"      # a valid embedding is stored
    FAILED = "FAILED"            # embedding generation/validation failed
