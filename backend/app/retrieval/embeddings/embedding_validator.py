"""Embedding validation (Phase 2A, task §7).

Defense-in-depth at the *persistence* boundary: even after the provider's
structural checks, validate every vector before we write it to pgvector. Mirrors
the Phase 1C `ChunkValidator` shape (fatal vs warning), and — critically — every
validation failure is logged.

Validated:
  * null / missing embedding            → fatal
  * incorrect dimension                 → fatal
  * empty vector                        → fatal
  * all-zero vector                     → fatal (meaningless for cosine similarity)
  * duplicate generation attempt        → fatal (chunk already COMPLETED)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.models.enums import EmbeddingStatus
from app.retrieval.embeddings.provider import Embedding

log = get_logger(__name__)


@dataclass
class EmbeddingValidationResult:
    fatal: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.fatal


class EmbeddingValidator:
    """Validates a vector destined for a chunk's `embedding` column."""

    def __init__(self, *, dimension: int) -> None:
        self.dimension = dimension

    def validate(
        self,
        *,
        embedding: Embedding | None,
        current_status: EmbeddingStatus | str | None = None,
        chunk_id: str | None = None,
    ) -> EmbeddingValidationResult:
        result = EmbeddingValidationResult()

        # Duplicate generation: chunk is already COMPLETED — re-embedding wastes
        # an API call and risks overwriting a good vector.
        status_value = (
            current_status.value
            if isinstance(current_status, EmbeddingStatus)
            else current_status
        )
        if status_value == EmbeddingStatus.COMPLETED.value:
            result.fatal.append("duplicate_generation")

        if embedding is None:
            result.fatal.append("null_embedding")
        elif len(embedding) == 0:
            result.fatal.append("empty_vector")
        else:
            if len(embedding) != self.dimension:
                result.fatal.append(
                    f"wrong_dimension: {len(embedding)} != {self.dimension}"
                )
            if all(x == 0.0 for x in embedding):
                result.fatal.append("zero_vector")
            elif any(not math.isfinite(x) for x in embedding):
                result.fatal.append("non_finite_values")

        if not result.is_valid:
            log.warning(
                "embedding.validation_failed",
                chunk_id=chunk_id,
                issues=result.fatal,
            )
        return result
