"""Unit tests for the persistence-layer embedding validator (Phase 2A)."""

from __future__ import annotations

import pytest
from app.models.enums import EmbeddingStatus
from app.retrieval.embeddings.embedding_validator import EmbeddingValidator

DIM = 768


def _vec(n: int = DIM, value: float = 0.1) -> list[float]:
    return [value] * n


@pytest.mark.unit
def test_valid_embedding_passes() -> None:
    v = EmbeddingValidator(dimension=DIM)
    res = v.validate(embedding=_vec())
    assert res.is_valid
    assert not res.fatal


@pytest.mark.unit
def test_null_embedding_is_fatal() -> None:
    v = EmbeddingValidator(dimension=DIM)
    res = v.validate(embedding=None)
    assert not res.is_valid and "null_embedding" in res.fatal


@pytest.mark.unit
def test_empty_vector_is_fatal() -> None:
    v = EmbeddingValidator(dimension=DIM)
    res = v.validate(embedding=[])
    assert not res.is_valid and "empty_vector" in res.fatal


@pytest.mark.unit
def test_wrong_dimension_is_fatal() -> None:
    v = EmbeddingValidator(dimension=DIM)
    res = v.validate(embedding=_vec(100))
    assert not res.is_valid
    assert any(f.startswith("wrong_dimension") for f in res.fatal)


@pytest.mark.unit
def test_zero_vector_is_fatal() -> None:
    v = EmbeddingValidator(dimension=DIM)
    res = v.validate(embedding=_vec(value=0.0))
    assert not res.is_valid and "zero_vector" in res.fatal


@pytest.mark.unit
def test_duplicate_generation_is_fatal() -> None:
    v = EmbeddingValidator(dimension=DIM)
    res = v.validate(embedding=_vec(), current_status=EmbeddingStatus.COMPLETED)
    assert not res.is_valid and "duplicate_generation" in res.fatal


@pytest.mark.unit
def test_non_completed_status_is_not_duplicate() -> None:
    v = EmbeddingValidator(dimension=DIM)
    res = v.validate(embedding=_vec(), current_status=EmbeddingStatus.PROCESSING)
    assert res.is_valid
