"""Unit tests for retrieval profiles (Phase 2C)."""

from __future__ import annotations

import pytest
from app.ingestion.section_detection.taxonomy import get_taxonomy
from app.retrieval.hybrid.retrieval_exceptions import UnknownProfileError
from app.retrieval.hybrid.retrieval_profiles import (
    PROFILES,
    get_profile,
    list_profiles,
)


@pytest.mark.unit
def test_expected_profiles_exist() -> None:
    assert {"GENERAL", "RISK_ANALYSIS", "MANAGEMENT_TONE", "FINANCIAL_STATEMENTS", "GUIDANCE"} <= set(
        PROFILES
    )


@pytest.mark.unit
def test_get_profile_default_is_general() -> None:
    assert get_profile(None).name == "GENERAL"
    assert get_profile("general").name == "GENERAL"  # case-insensitive


@pytest.mark.unit
def test_unknown_profile_raises() -> None:
    with pytest.raises(UnknownProfileError):
        get_profile("DOES_NOT_EXIST")


@pytest.mark.unit
def test_general_has_no_preferred_sections() -> None:
    assert get_profile("GENERAL").preferred_sections == ()


@pytest.mark.unit
def test_risk_profile_prefers_risk_sections() -> None:
    assert "Risk Factors" in get_profile("RISK_ANALYSIS").preferred_sections


@pytest.mark.unit
def test_profile_preferred_sections_are_canonical() -> None:
    tax = get_taxonomy()
    for p in list_profiles():
        for section in p.preferred_sections:
            assert tax.is_canonical(section), f"{p.name}: '{section}' not canonical"


@pytest.mark.unit
def test_profiles_have_search_parameters() -> None:
    for p in list_profiles():
        assert p.default_top_k >= 1
        assert p.max_candidates >= 1
        assert isinstance(p.as_dict()["preferred_sections"], list)
