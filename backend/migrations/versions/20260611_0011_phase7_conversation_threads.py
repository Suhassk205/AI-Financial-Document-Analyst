"""Phase 7 — conversation_threads + conversation_messages

Revision ID: 0011_phase7
Revises: 0010_phase5
Create Date: 2026-06-11

Adds `conversation_threads` and `conversation_messages` tables. Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0011_phase7"
down_revision: str | None = "0010_phase5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- conversation_threads -----------------------------------------------
    op.create_table(
        "conversation_threads",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "thread_id", sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_conversation_threads_thread_id",
        "conversation_threads",
        ["thread_id"],
        unique=True,
    )

    # ---- conversation_messages ----------------------------------------------
    op.create_table(
        "conversation_messages",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "thread_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversation_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role", sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "content", sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "metadata", postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_conversation_messages_thread_id",
        "conversation_messages",
        ["thread_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_conversation_messages_thread_id", table_name="conversation_messages")
    op.drop_table("conversation_messages")
    op.drop_index("ix_conversation_threads_thread_id", table_name="conversation_threads")
    op.drop_table("conversation_threads")
