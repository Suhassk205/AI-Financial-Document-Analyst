"""Retrieval profiles (Phase 2C).

A profile bundles retrieval configuration for a downstream task: which sections to
prefer, a default result count, and a candidate guardrail. Profiles only *prefer*
sections — they apply as a filter when the caller didn't pin a section, and never
override an explicit one. Section names are canonical taxonomy names (Phase 1B).

These exist to prepare future phases (risk/tone/metrics agents) — in Phase 2C they
softly scope hybrid search; they introduce NO reasoning or generation.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.retrieval.hybrid.retrieval_exceptions import UnknownProfileError


@dataclass(frozen=True)
class RetrievalProfile:
    name: str
    description: str
    preferred_sections: tuple[str, ...]   # canonical normalized_section_name values
    default_top_k: int
    max_candidates: int                   # guardrail / search parameter

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "preferred_sections": list(self.preferred_sections),
            "default_top_k": self.default_top_k,
            "max_candidates": self.max_candidates,
        }


PROFILES: dict[str, RetrievalProfile] = {
    "GENERAL": RetrievalProfile(
        name="GENERAL",
        description="No section preference — search across all content.",
        preferred_sections=(),
        default_top_k=10,
        max_candidates=5000,
    ),
    "RISK_ANALYSIS": RetrievalProfile(
        name="RISK_ANALYSIS",
        description="Prefer risk disclosures.",
        preferred_sections=("Risk Factors", "Market Risk Disclosures", "Legal Proceedings"),
        default_top_k=10,
        max_candidates=2000,
    ),
    "MANAGEMENT_TONE": RetrievalProfile(
        name="MANAGEMENT_TONE",
        description="Prefer management commentary and earnings-call remarks.",
        preferred_sections=(
            "Management Commentary", "CEO Commentary", "CFO Commentary",
            "Prepared Remarks", "Question & Answer",
        ),
        default_top_k=10,
        max_candidates=2000,
    ),
    "FINANCIAL_STATEMENTS": RetrievalProfile(
        name="FINANCIAL_STATEMENTS",
        description="Prefer the financial statements and their notes.",
        preferred_sections=(
            "Financial Statements", "Balance Sheet", "Income Statement",
            "Cash Flow Statement", "Notes to Financial Statements",
        ),
        default_top_k=10,
        max_candidates=2000,
    ),
    "GUIDANCE": RetrievalProfile(
        name="GUIDANCE",
        description="Prefer forward-looking guidance and MD&A.",
        preferred_sections=("Forward Guidance", "MD&A"),
        default_top_k=10,
        max_candidates=2000,
    ),
}

DEFAULT_PROFILE = "GENERAL"


def get_profile(name: str | None) -> RetrievalProfile:
    key = (name or DEFAULT_PROFILE).upper()
    profile = PROFILES.get(key)
    if profile is None:
        raise UnknownProfileError(
            f"unknown retrieval profile '{name}'",
            details={"allowed": sorted(PROFILES.keys())},
        )
    return profile


def list_profiles() -> list[RetrievalProfile]:
    return list(PROFILES.values())
