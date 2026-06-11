"""Unit tests for embedding status enums (Phase 2A)."""

from __future__ import annotations

import pytest
from app.models.enums import EmbeddingStatus, ReportStatus


@pytest.mark.unit
def test_embedding_status_values() -> None:
    assert {s.value for s in EmbeddingStatus} == {
        "PENDING",
        "PROCESSING",
        "COMPLETED",
        "FAILED",
    }


@pytest.mark.unit
def test_report_status_has_embedding_states() -> None:
    assert ReportStatus.EMBEDDING.value == "EMBEDDING"
    assert ReportStatus.EMBEDDED.value == "EMBEDDED"
    # ordering: embedding comes after chunking in the pipeline lifecycle
    values = [s.value for s in ReportStatus]
    assert values.index("EMBEDDING") > values.index("CHUNKED")


@pytest.mark.unit
def test_embedding_status_is_str_enum() -> None:
    # Stored as VARCHAR; the enum must compare/serialize as its string value.
    assert EmbeddingStatus.COMPLETED == "COMPLETED"
    assert EmbeddingStatus.PENDING.value == "PENDING"
