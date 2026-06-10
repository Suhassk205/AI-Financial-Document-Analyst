"""Phase 1A — ingestion baseline: companies, reports, report_pages

Revision ID: 0001_phase1a
Revises:
Create Date: 2026-06-10

Creates the Phase 1A ingestion schema. Enums are stored as VARCHAR + CHECK
(native_enum=False) to match the ORM and keep value evolution to simple migrations.
The pgvector column and embedding dimension are intentionally NOT introduced here
(deferred to Phase 2 — see docs/02_DATABASE_DESIGN.md §6.1).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_phase1a"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REPORT_TYPES = ("10-K", "10-Q", "TRANSCRIPT", "OTHER")
REPORT_STATUSES = ("UPLOADED", "PROCESSING", "PROCESSED", "FAILED")


def upgrade() -> None:
    # ---- companies ----------------------------------------------------------
    op.create_table(
        "companies",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=True),
        sa.Column("sector", sa.Text(), nullable=True),
        sa.Column("industry", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_companies"),
        sa.UniqueConstraint("ticker", name="uq_companies_ticker"),
    )

    # ---- reports ------------------------------------------------------------
    op.create_table(
        "reports",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "report_type",
            sa.Enum(*REPORT_TYPES, native_enum=False, length=16, name="report_type"),
            nullable=False,
        ),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("quarter", sa.Integer(), nullable=True),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(*REPORT_STATUSES, native_enum=False, length=16, name="report_status"),
            server_default="UPLOADED",
            nullable=False,
        ),
        sa.Column("total_pages", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_reports"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_reports_company_id_companies",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("quarter IS NULL OR (quarter BETWEEN 1 AND 4)", name="ck_reports_quarter_range"),
        sa.CheckConstraint("year BETWEEN 1900 AND 2200", name="ck_reports_year_range"),
        sa.CheckConstraint("total_pages IS NULL OR total_pages >= 0", name="ck_reports_total_pages_nonneg"),
    )
    op.create_index("ix_reports_company_id", "reports", ["company_id"])
    op.create_index("ix_reports_status", "reports", ["status"])
    op.create_index("ix_reports_uploaded_at", "reports", ["uploaded_at"])

    # ---- report_pages -------------------------------------------------------
    op.create_table(
        "report_pages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("page_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_report_pages"),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["reports.id"],
            name="fk_report_pages_report_id_reports",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("report_id", "page_number", name="uq_report_page_number"),
    )


def downgrade() -> None:
    op.drop_table("report_pages")
    op.drop_index("ix_reports_uploaded_at", table_name="reports")
    op.drop_index("ix_reports_status", table_name="reports")
    op.drop_index("ix_reports_company_id", table_name="reports")
    op.drop_table("reports")
    op.drop_table("companies")
