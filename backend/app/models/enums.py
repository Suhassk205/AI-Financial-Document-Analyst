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
    EXTRACTING = "EXTRACTING"    # worker is extracting financial metrics (Phase 3A)
    EXTRACTED = "EXTRACTED"      # financial metrics extracted and stored (Phase 3A done)
    COMPARING = "COMPARING"      # worker is generating period comparisons (Phase 3B)
    COMPARED = "COMPARED"        # period comparisons generated and stored (Phase 3B done)
    ANALYZING = "ANALYZING"      # worker is generating financial analytics (Phase 3C)
    ANALYZED = "ANALYZED"        # financial analytics generated and stored (Phase 3C done)
    RISK_EXTRACTING = "RISK_EXTRACTING"  # worker is extracting risks (Phase 4)
    RISK_EXTRACTED = "RISK_EXTRACTED"    # risks extracted and stored (Phase 4 done)
    TONE_EXTRACTING = "TONE_EXTRACTING"  # worker is extracting management tone (Phase 5)
    TONE_EXTRACTED = "TONE_EXTRACTED"    # management tone extracted and stored (Phase 5 done)
    FAILED = "FAILED"            # a processing step failed (see error_message / logs)


class ComparisonType(str, Enum):
    """Period-over-period comparison kinds (Phase 3B).

    Phase 3B generates YOY and QOQ deterministically; YTD/TTM are reserved for
    future extensibility (enum-only — not generated yet).
    """

    YOY = "YOY"   # year over year (same quarter, prior year; or FY vs prior FY)
    QOQ = "QOQ"   # quarter over quarter (prior quarter)
    YTD = "YTD"   # year to date (reserved)
    TTM = "TTM"   # trailing twelve months (reserved)


class ComparisonStatus(str, Enum):
    """Lifecycle of a comparison-generation run (Phase 3B) — operational visibility."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ExtractionMethod(str, Enum):
    """How a financial metric value was obtained (Phase 3A) — for auditability.

    The LLM is never the source of truth (ADR-007/ADR-017): every value passes
    deterministic validation, and the method records how it was derived.
    """

    RULE_BASED = "RULE_BASED"            # deterministic regex/pattern extraction
    LLM_BASED = "LLM_BASED"              # LLM structured extraction (validated)
    HYBRID_VALIDATED = "HYBRID_VALIDATED"  # rule + LLM agreed → highest confidence


class MetricCategory(str, Enum):
    """Top-level grouping for a financial metric (Phase 3A)."""

    REVENUE = "REVENUE"
    PROFITABILITY = "PROFITABILITY"
    MARGINS = "MARGINS"
    CASH_FLOW = "CASH_FLOW"
    DEBT = "DEBT"
    CAPEX = "CAPEX"
    GUIDANCE = "GUIDANCE"
    OTHER = "OTHER"


class EmbeddingStatus(str, Enum):
    """Per-chunk embedding lifecycle (Phase 2A) — operational visibility.

    Tracked on `document_chunks.embedding_status` so we can answer
    "does every chunk have a valid embedding?" and locate stragglers/failures.
    """

    PENDING = "PENDING"          # chunk exists, no embedding yet
    PROCESSING = "PROCESSING"    # embedding is being generated for this chunk
    COMPLETED = "COMPLETED"      # a valid embedding is stored
    FAILED = "FAILED"            # embedding generation/validation failed


class RiskCategory(str, Enum):
    """Canonical risk categories (Phase 4)."""

    SUPPLY_CHAIN = "SUPPLY_CHAIN"
    REGULATORY = "REGULATORY"
    MARKET = "MARKET"
    COMPETITION = "COMPETITION"
    TECHNOLOGY = "TECHNOLOGY"
    CYBERSECURITY = "CYBERSECURITY"
    OPERATIONAL = "OPERATIONAL"
    LIQUIDITY = "LIQUIDITY"
    GEOPOLITICAL = "GEOPOLITICAL"
    LEGAL = "LEGAL"
    ENVIRONMENTAL = "ENVIRONMENTAL"
    REPUTATION = "REPUTATION"
    MACROECONOMIC = "MACROECONOMIC"
    OTHER = "OTHER"


class RiskSeverity(str, Enum):
    """Risk severity levels (Phase 4)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskEvolutionType(str, Enum):
    """Risk evolution classification (Phase 4)."""

    NEW_RISK = "NEW_RISK"
    REMOVED_RISK = "REMOVED_RISK"
    UNCHANGED_RISK = "UNCHANGED_RISK"
    ESCALATED_RISK = "ESCALATED_RISK"
    REDUCED_RISK = "REDUCED_RISK"


class Sentiment(str, Enum):
    """Sentiment classification for management tone (Phase 5)."""

    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"


class ConfidenceLevel(str, Enum):
    """Confidence level classification for management tone (Phase 5)."""

    VERY_CONFIDENT = "VERY_CONFIDENT"
    CONFIDENT = "CONFIDENT"
    CAUTIOUS = "CAUTIOUS"
    VERY_CAUTIOUS = "VERY_CAUTIOUS"


class ToneEvolutionType(str, Enum):
    """Tone evolution classification for period-over-period changes (Phase 5)."""

    MORE_POSITIVE = "MORE_POSITIVE"
    MORE_NEGATIVE = "MORE_NEGATIVE"
    MORE_CONFIDENT = "MORE_CONFIDENT"
    LESS_CONFIDENT = "LESS_CONFIDENT"
    MORE_CAUTIOUS = "MORE_CAUTIOUS"
    LESS_CAUTIOUS = "LESS_CAUTIOUS"
    UNCHANGED = "UNCHANGED"

