"""Phase 2A — chunk embeddings (pgvector) + embedding status tracking

Revision ID: 0004_phase2a
Revises: 0003_phase1c
Create Date: 2026-06-11

Adds the embedding columns to `document_chunks` and extends `reports.status`
with the EMBEDDING / EMBEDDED states.

Embedding model finalized in Phase 2A (ADR-013): **gemini-embedding-001**.
The dimension (**768**) was determined by calling the live model and observing
its output (native 3072, Matryoshka-truncated to 768 + re-normalized), NOT from
documentation. 768 keeps the column within pgvector's 2000-dim HNSW/IVFFlat
index limit so Phase 2B can index a plain `vector(768)`.

IMPORTANT: this migration creates **no ANN index** (no HNSW, no IVFFlat). Vector
similarity indexing is deferred to Phase 2B. The only index added here is a plain
btree on (report_id, embedding_status) for operational "which chunks still need
embeddings?" lookups.

Production-safe: the new vector column is NULLable (existing chunks keep working
and are embedded asynchronously), `embedding_status` defaults to 'PENDING', and
the migration is fully reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "0004_phase2a"
down_revision: str | None = "0003_phase1c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Verified Gemini embedding dimension (see module docstring / ADR-013).
EMBEDDING_DIM = 768

_PREV_STATUSES = (
    "UPLOADED", "PROCESSING", "PROCESSED", "SECTIONING", "SECTIONED",
    "CHUNKING", "CHUNKED", "FAILED",
)
_NEW_STATUSES = (
    "UPLOADED", "PROCESSING", "PROCESSED", "SECTIONING", "SECTIONED",
    "CHUNKING", "CHUNKED", "EMBEDDING", "EMBEDDED", "FAILED",
)


def _status_check(values: tuple[str, ...]) -> str:
    return "status IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    # pgvector must exist before adding a vector column. init.sql enables it on
    # first boot; this makes the migration self-contained for fresh databases too.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ---- embedding columns on document_chunks -------------------------------
    op.add_column(
        "document_chunks",
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column(
            "embedding_status",
            sa.String(length=16),
            nullable=False,
            server_default="PENDING",
        ),
    )
    op.add_column(
        "document_chunks",
        sa.Column("embedding_model", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("embedding_generated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Bare constraint name — Alembic applies the `ck_%(table_name)s_%(constraint_name)s`
    # naming convention, yielding `ck_document_chunks_embedding_status` (matches the
    # ORM model, so the downgrade drop_constraint resolves correctly).
    op.create_check_constraint(
        "embedding_status",
        "document_chunks",
        "embedding_status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')",
    )

    # Operational (NOT ANN) index for status sweeps. Phase 2B adds the vector index.
    op.create_index(
        "ix_document_chunks_embedding_status",
        "document_chunks",
        ["report_id", "embedding_status"],
    )

    # ---- extend reports.status allowed values -------------------------------
    op.execute("ALTER TABLE reports DROP CONSTRAINT IF EXISTS ck_reports_report_status")
    op.create_check_constraint(
        "report_status", "reports", _status_check(_NEW_STATUSES)
    )


def downgrade() -> None:
    # Revert reports.status first (drop EMBEDDING/EMBEDDED). Any rows in those
    # states would violate the narrower constraint; in practice downgrades run
    # against pre-Phase-2A data, but guard defensively by parking them as FAILED.
    op.execute(
        "UPDATE reports SET status = 'FAILED' "
        "WHERE status IN ('EMBEDDING', 'EMBEDDED')"
    )
    op.execute("ALTER TABLE reports DROP CONSTRAINT IF EXISTS ck_reports_report_status")
    op.create_check_constraint(
        "report_status", "reports", _status_check(_PREV_STATUSES)
    )

    op.drop_index("ix_document_chunks_embedding_status", table_name="document_chunks")
    # Bare name — drop_constraint also applies the naming convention (→
    # ck_document_chunks_embedding_status, matching what upgrade created).
    op.drop_constraint("embedding_status", "document_chunks", type_="check")
    op.drop_column("document_chunks", "embedding_generated_at")
    op.drop_column("document_chunks", "embedding_model")
    op.drop_column("document_chunks", "embedding_status")
    op.drop_column("document_chunks", "embedding")
