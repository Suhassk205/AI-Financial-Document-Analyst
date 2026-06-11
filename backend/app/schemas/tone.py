"""Pydantic schemas for management tone and tone evolution API endpoints (Phase 5)."""

from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel, Field

from app.models.enums import Sentiment, ConfidenceLevel, ToneEvolutionType


class ManagementToneBase(BaseModel):
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


class ManagementToneCreate(ManagementToneBase):
    company_id: uuid.UUID
    report_id: uuid.UUID
    source_chunk_id: uuid.UUID | None = None


class ManagementToneResponse(ManagementToneBase):
    id: uuid.UUID
    company_id: uuid.UUID
    report_id: uuid.UUID
    source_chunk_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ToneEvolutionResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    current_tone_id: uuid.UUID | None = None
    previous_tone_id: uuid.UUID | None = None
    evolution_type: ToneEvolutionType
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    explanation: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ToneSectionSummary(BaseModel):
    source_type: str
    average_positive_score: float
    average_negative_score: float
    average_hedging_score: float
    average_confidence_score: float
    dominant_sentiment: Sentiment
    record_count: int


class CompanyToneSummary(BaseModel):
    company_id: uuid.UUID
    total_tone_records: int
    overall_average_positive: float
    overall_average_negative: float
    overall_average_hedging: float
    overall_average_confidence: float
    sections: list[ToneSectionSummary] = Field(default_factory=list)
