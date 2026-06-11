"""Data models for management tone extraction (Phase 5)."""

from __future__ import annotations

import uuid
from pydantic import BaseModel, Field

from app.models.enums import Sentiment, ConfidenceLevel


class ToneChunkInput(BaseModel):
    """Input chunk for tone analysis."""

    chunk_id: str
    text: str
    normalized_section_name: str | None = None
    fiscal_year: int | None = None
    fiscal_quarter: int | None = None


class ToneCandidate(BaseModel):
    """Temporary tone analysis candidate (produced by rule or LLM analyzer)."""

    source_chunk_id: str | None = None
    source_type: str  # e.g., MD&A, CEO Commentary
    sentiment: Sentiment
    confidence_level: ConfidenceLevel
    hedging_score: float = Field(..., ge=0.0, le=1.0)
    positive_score: float = Field(..., ge=0.0, le=1.0)
    negative_score: float = Field(..., ge=0.0, le=1.0)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    source_text: str
    extraction_method: str
    extraction_metadata: dict = Field(default_factory=dict)

    def key(self) -> str:
        """Deterministic grouping key based on source type."""
        return self.source_type.upper().strip()


class ExtractedTone(BaseModel):
    """Final validated tone record to be stored in the database."""

    company_id: uuid.UUID
    source_chunk_id: uuid.UUID | None = None
    source_type: str
    sentiment: Sentiment
    confidence_level: ConfidenceLevel
    hedging_score: float = Field(..., ge=0.0, le=1.0)
    positive_score: float = Field(..., ge=0.0, le=1.0)
    negative_score: float = Field(..., ge=0.0, le=1.0)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    extraction_method: str
    source_text: str
    extraction_metadata: dict = Field(default_factory=dict)


class ToneExtractionStats(BaseModel):
    """Statistics on a tone extraction execution run."""

    chunks_processed: int = 0
    rule_hits: int = 0
    llm_hits: int = 0
    agreements: int = 0
    disagreements: int = 0
    validation_failures: int = 0
    llm_errors: int = 0
    duration_seconds: float = 0.0

    def as_dict(self) -> dict:
        return self.model_dump()


class ToneExtractionResult(BaseModel):
    """Full results of a tone extraction run, including records and run stats."""

    tone_records: list[ExtractedTone] = Field(default_factory=list)
    stats: ToneExtractionStats = Field(default_factory=ToneExtractionStats)
