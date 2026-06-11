"""Phase 1C — document_chunks + extended report status check

Revision ID: 0003_phase1c
Revises: 0002_phase1b
Create Date: 2026-06-10

Adds the `document_chunks` table (retrieval-ready knowledge chunks) and extends
the `reports.status` CHECK constraint with the CHUNKING / CHUNKED states.

IMPORTANT: this table intentionally has NO embedding / vector column and NO
pgvector index — embeddings and the `vector(EMBEDDING_DIM)` column are introduced
in Phase 2 (see docs/02_DATABASE_DESIGN.md §6.1).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_phase1c"
down_revision: str | None = "0002_phase1b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREV_STATUSES = ("UPLOADED", "PROCESSING", "PROCESSED", "SECTIONING", "SECTIONED", "FAILED")
_NEW_STATUSES = (
    "UPLOADED", "PROCESSING", "PROCESSED", "SECTIONING", "SECTIONED",
    "CHUNKING", "CHUNKED", "FAILED",
)


def _status_check(values: tuple[str, ...]) -> str:
    return "status IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    # ---- extend reports.status allowed values -------------------------------
    op.execute("ALTER TABLE reports DROP CONSTRAINT IF EXISTS ck_reports_report_status")
    op.create_check_constraint(
        "report_status", "reports", _status_check(_NEW_STATUSES)
    )

    # ---- document_chunks ----------------------------------------------------
    op.create_table(
        "document_chunks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("start_page", sa.Integer(), nullable=True),
        sa.Column("end_page", sa.Integer(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_document_chunks"),
        sa.ForeignKeyConstraint(
            ["report_id"], ["reports.id"],
            name="fk_document_chunks_report_id_reports", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["section_id"], ["report_sections.id"],
            name="fk_document_chunks_section_id_report_sections", ondelete="SET NULL",
        ),
        sa.UniqueConstraint("report_id", "chunk_index", name="uq_document_chunks_report_index"),
        sa.CheckConstraint("token_count >= 0", name="ck_document_chunks_token_count"),
        sa.CheckConstraint("chunk_index >= 0", name="ck_document_chunks_index"),
    )
    op.create_index("ix_document_chunks_report_id", "document_chunks", ["report_id"])
    op.create_index("ix_document_chunks_section_id", "document_chunks", ["section_id"])
    op.create_index(
        "ix_document_chunks_metadata",
        "document_chunks",
        ["metadata"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_metadata", table_name="document_chunks")
    op.drop_index("ix_document_chunks_section_id", table_name="document_chunks")
    op.drop_index("ix_document_chunks_report_id", table_name="document_chunks")
    op.drop_table("document_chunks")

    op.execute("ALTER TABLE reports DROP CONSTRAINT IF EXISTS ck_reports_report_status")
    op.create_check_constraint(
        "report_status", "reports", _status_check(_PREV_STATUSES)
    )
