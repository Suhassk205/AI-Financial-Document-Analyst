"""Phase 1B — report_sections + extended report status check

Revision ID: 0002_phase1b
Revises: 0001_phase1a
Create Date: 2026-06-10

Adds the `report_sections` table (logical sections detected from a report) and
extends the `reports.status` CHECK constraint with the SECTIONING / SECTIONED
states introduced for the section-detection pipeline.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_phase1b"
down_revision: str | None = "0001_phase1a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_STATUSES = ("UPLOADED", "PROCESSING", "PROCESSED", "FAILED")
_NEW_STATUSES = ("UPLOADED", "PROCESSING", "PROCESSED", "SECTIONING", "SECTIONED", "FAILED")


def _status_check(values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"status IN ({joined})"


def upgrade() -> None:
    # ---- extend reports.status allowed values -------------------------------
    # Drop whatever non-native-enum CHECK exists (name differs by how it was
    # created), then add a deterministically-named one with the new values.
    op.execute("ALTER TABLE reports DROP CONSTRAINT IF EXISTS report_status")
    op.execute("ALTER TABLE reports DROP CONSTRAINT IF EXISTS ck_reports_report_status")
    op.create_check_constraint(
        "report_status", "reports", _status_check(_NEW_STATUSES)
    )

    # ---- report_sections ----------------------------------------------------
    op.create_table(
        "report_sections",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_name", sa.Text(), nullable=False),
        sa.Column("normalized_section_name", sa.Text(), nullable=False),
        sa.Column("start_page", sa.Integer(), nullable=False),
        sa.Column("end_page", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_report_sections"),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["reports.id"],
            name="fk_report_sections_report_id_reports",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("confidence_score BETWEEN 0 AND 1", name="ck_report_sections_confidence"),
        sa.CheckConstraint("start_page >= 1", name="ck_report_sections_start_page"),
        sa.CheckConstraint("end_page >= start_page", name="ck_report_sections_page_order"),
    )
    op.create_index("ix_report_sections_report_id", "report_sections", ["report_id"])
    op.create_index(
        "ix_report_sections_normalized_name", "report_sections", ["normalized_section_name"]
    )


def downgrade() -> None:
    op.drop_index("ix_report_sections_normalized_name", table_name="report_sections")
    op.drop_index("ix_report_sections_report_id", table_name="report_sections")
    op.drop_table("report_sections")

    # Revert status values (will fail if any row uses SECTIONING/SECTIONED).
    op.execute("ALTER TABLE reports DROP CONSTRAINT IF EXISTS ck_reports_report_status")
    op.create_check_constraint(
        "report_status", "reports", _status_check(_OLD_STATUSES)
    )
