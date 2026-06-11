"""Metadata filter builder (Phase 2C).

Translates a `RetrievalContext` into SQLAlchemy WHERE conditions used to constrain
the candidate set BEFORE similarity ranking.

Filter sources:
  * report-level facts (company_id, year, quarter, report_type) → typed, btree-
    indexed columns on `reports` (join), so comparisons are exact and fast;
  * report_id → direct on `document_chunks` (FK-indexed);
  * section_name / normalized_section_name → the per-chunk denormalized JSONB
    `metadata` via `@>` containment, which uses the existing GIN index.

All filters are optional and AND-combined.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import or_

from app.models.document_chunk import DocumentChunk
from app.models.enums import ReportType
from app.models.report import Report
from app.retrieval.hybrid.query_context import RetrievalContext


@dataclass
class FilterPlan:
    conditions: list[Any] = field(default_factory=list)
    needs_report_join: bool = False
    applied: dict = field(default_factory=dict)


def _section_eq(name: str):
    return DocumentChunk.chunk_metadata.contains({"normalized_section_name": name})


def build_filter_plan(
    ctx: RetrievalContext, *, preferred_sections: tuple[str, ...] = ()
) -> FilterPlan:
    """Build WHERE conditions for a context (+ optional profile preferred sections)."""
    plan = FilterPlan()

    if ctx.report_id is not None:
        plan.conditions.append(DocumentChunk.report_id == ctx.report_id)
        plan.applied["report_id"] = str(ctx.report_id)

    if ctx.company_id is not None:
        plan.conditions.append(Report.company_id == ctx.company_id)
        plan.needs_report_join = True
        plan.applied["company_id"] = str(ctx.company_id)

    if ctx.year is not None:
        plan.conditions.append(Report.year == ctx.year)
        plan.needs_report_join = True
        plan.applied["year"] = ctx.year

    if ctx.quarter is not None:
        plan.conditions.append(Report.quarter == ctx.quarter)
        plan.needs_report_join = True
        plan.applied["quarter"] = ctx.quarter

    if ctx.report_type is not None:
        plan.conditions.append(Report.report_type == ReportType(ctx.report_type))
        plan.needs_report_join = True
        plan.applied["report_type"] = ctx.report_type

    if ctx.section_name is not None:
        plan.conditions.append(
            DocumentChunk.chunk_metadata.contains({"section_name": ctx.section_name})
        )
        plan.applied["section_name"] = ctx.section_name

    if ctx.normalized_section_name is not None:
        plan.conditions.append(_section_eq(ctx.normalized_section_name))
        plan.applied["normalized_section_name"] = ctx.normalized_section_name
    elif preferred_sections:
        # Profile preference applies ONLY when the caller didn't pin a section.
        plan.conditions.append(or_(*[_section_eq(s) for s in preferred_sections]))
        plan.applied["preferred_sections"] = list(preferred_sections)

    return plan
