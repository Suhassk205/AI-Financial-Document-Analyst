"""Phase 5 — management_tone + tone_evolution + extended report status

Revision ID: 0010_phase5
Revises: 0009_phase4
Create Date: 2026-06-11

Adds `management_tone` and `tone_evolution` tables, and extends `reports.status` with
TONE_EXTRACTING / TONE_EXTRACTED. Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0010_phase5"
down_revision: str | None = "0009_phase4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREV_STATUSES = (
    "UPLOADED", "PROCESSING", "PROCESSED", "SECTIONING", "SECTIONED",
    "CHUNKING", "CHUNKED", "EMBEDDING", "EMBEDDED", "EXTRACTING", "EXTRACTED",
    "COMPARING", "COMPARED", "ANALYZING", "ANALYZED", "RISK_EXTRACTING", "RISK_EXTRACTED", "FAILED",
)
_NEW_STATUSES = (
    "UPLOADED", "PROCESSING", "PROCESSED", "SECTIONING", "SECTIONED",
    "CHUNKING", "CHUNKED", "EMBEDDING", "EMBEDDED", "EXTRACTING", "EXTRACTED",
    "COMPARING", "COMPARED", "ANALYZING", "ANALYZED",
    "RISK_EXTRACTING", "RISK_EXTRACTED",
    "TONE_EXTRACTING", "TONE_EXTRACTED", "FAILED",
)

_SENTIMENTS = ("POSITIVE", "NEUTRAL", "NEGATIVE")
_CONFIDENCE_LEVELS = ("VERY_CONFIDENT", "CONFIDENT", "CAUTIOUS", "VERY_CAUTIOUS")
_EVOLUTION_TYPES = (
    "MORE_POSITIVE", "MORE_NEGATIVE", "MORE_CONFIDENT", "LESS_CONFIDENT",
    "MORE_CAUTIOUS", "LESS_CAUTIOUS", "UNCHANGED",
)
_METHODS = ("RULE_BASED", "LLM_BASED", "HYBRID_VALIDATED")


def _in_list(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


def _status_check(values: tuple[str, ...]) -> str:
    return "status IN " + _in_list(values)


def upgrade() -> None:
    # ---- management_tone ----------------------------------------------------
    op.create_table(
        "management_tone",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), nullable=False,
        ),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_chunk_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("sentiment", sa.String(length=10), nullable=False),
        sa.Column("confidence_level", sa.String(length=20), nullable=False),
        sa.Column("hedging_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("positive_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("negative_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("confidence_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("extraction_method", sa.String(length=20), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_management_tone"),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"],
            name="fk_management_tone_company", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["report_id"], ["reports.id"],
            name="fk_management_tone_report", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_chunk_id"], ["document_chunks.id"],
            name="fk_management_tone_chunk", ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "hedging_score BETWEEN 0 AND 1",
            name="ck_management_tone_hedging",
        ),
        sa.CheckConstraint(
            "positive_score BETWEEN 0 AND 1",
            name="ck_management_tone_positive",
        ),
        sa.CheckConstraint(
            "negative_score BETWEEN 0 AND 1",
            name="ck_management_tone_negative",
        ),
        sa.CheckConstraint(
            "confidence_score BETWEEN 0 AND 1",
            name="ck_management_tone_confidence",
        ),
        sa.CheckConstraint(
            f"sentiment IN {_in_list(_SENTIMENTS)}",
            name="ck_management_tone_sentiment",
        ),
        sa.CheckConstraint(
            f"confidence_level IN {_in_list(_CONFIDENCE_LEVELS)}",
            name="ck_management_tone_confidence_level",
        ),
        sa.CheckConstraint(
            f"extraction_method IN {_in_list(_METHODS)}",
            name="ck_management_tone_method",
        ),
    )
    op.create_index("ix_management_tone_company_id", "management_tone", ["company_id"])
    op.create_index("ix_management_tone_report_id", "management_tone", ["report_id"])
    op.create_index("ix_management_tone_source_chunk_id", "management_tone", ["source_chunk_id"])
    op.create_index("ix_management_tone_sentiment", "management_tone", ["sentiment"])
    op.create_index("ix_management_tone_confidence_level", "management_tone", ["confidence_level"])

    # ---- tone_evolution -----------------------------------------------------
    op.create_table(
        "tone_evolution",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), nullable=False,
        ),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("current_tone_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("previous_tone_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evolution_type", sa.String(length=20), nullable=False),
        sa.Column("confidence_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_tone_evolution"),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"],
            name="fk_tone_evolution_company", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["current_tone_id"], ["management_tone.id"],
            name="fk_tone_evolution_current", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["previous_tone_id"], ["management_tone.id"],
            name="fk_tone_evolution_previous", ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "confidence_score BETWEEN 0 AND 1",
            name="ck_tone_evolution_confidence",
        ),
        sa.CheckConstraint(
            f"evolution_type IN {_in_list(_EVOLUTION_TYPES)}",
            name="ck_tone_evolution_type",
        ),
    )
    op.create_index("ix_tone_evolution_company_id", "tone_evolution", ["company_id"])
    op.create_index("ix_tone_evolution_current_tone_id", "tone_evolution", ["current_tone_id"])
    op.create_index("ix_tone_evolution_previous_tone_id", "tone_evolution", ["previous_tone_id"])

    # ---- extend report status -----------------------------------------------
    op.execute("ALTER TABLE reports DROP CONSTRAINT IF EXISTS ck_reports_report_status")
    op.create_check_constraint("report_status", "reports", _status_check(_NEW_STATUSES))


def downgrade() -> None:
    # revert report status
    op.execute(
        "UPDATE reports SET status = 'FAILED' "
        "WHERE status IN ('TONE_EXTRACTING', 'TONE_EXTRACTED')"
    )
    op.execute("ALTER TABLE reports DROP CONSTRAINT IF EXISTS ck_reports_report_status")
    op.create_check_constraint("report_status", "reports", _status_check(_PREV_STATUSES))

    # drop evolution
    op.drop_index("ix_tone_evolution_previous_tone_id", table_name="tone_evolution")
    op.drop_index("ix_tone_evolution_current_tone_id", table_name="tone_evolution")
    op.drop_index("ix_tone_evolution_company_id", table_name="tone_evolution")
    op.drop_table("tone_evolution")

    # drop management_tone
    op.drop_index("ix_management_tone_confidence_level", table_name="management_tone")
    op.drop_index("ix_management_tone_sentiment", table_name="management_tone")
    op.drop_index("ix_management_tone_source_chunk_id", table_name="management_tone")
    op.drop_index("ix_management_tone_report_id", table_name="management_tone")
    op.drop_index("ix_management_tone_company_id", table_name="management_tone")
    op.drop_table("management_tone")
