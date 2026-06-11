"""Embedding infrastructure (Phase 2A).

Converts `document_chunks` into pgvector embeddings using Gemini, and stores +
tracks them. This package is **generation + storage + operational monitoring
only** — NOT similarity search, NOT retrieval, NOT RAG (those are Phase 2B+).

Public surface:

    from app.retrieval.embeddings import (
        EmbeddingProvider,
        GeminiEmbeddingProvider,
        EmbeddingService,
        EmbeddingValidator,
        BatchProcessor,
        EmbeddingMetrics,
    )
"""

from app.retrieval.embeddings.batch_processor import BatchItem, BatchOutcome, BatchProcessor
from app.retrieval.embeddings.embedding_service import EmbeddingService
from app.retrieval.embeddings.embedding_validator import (
    EmbeddingValidationResult,
    EmbeddingValidator,
)
from app.retrieval.embeddings.exceptions import (
    EmbeddingConfigError,
    EmbeddingError,
    EmbeddingProviderError,
    InvalidEmbeddingResponseError,
    RateLimitError,
    TransientProviderError,
)
from app.retrieval.embeddings.gemini_provider import GeminiEmbeddingProvider
from app.retrieval.embeddings.metrics import EmbeddingMetrics
from app.retrieval.embeddings.provider import Embedding, EmbeddingProvider

__all__ = [
    "Embedding",
    "EmbeddingProvider",
    "GeminiEmbeddingProvider",
    "EmbeddingService",
    "EmbeddingValidator",
    "EmbeddingValidationResult",
    "BatchProcessor",
    "BatchItem",
    "BatchOutcome",
    "EmbeddingMetrics",
    "EmbeddingError",
    "EmbeddingConfigError",
    "EmbeddingProviderError",
    "RateLimitError",
    "TransientProviderError",
    "InvalidEmbeddingResponseError",
]
