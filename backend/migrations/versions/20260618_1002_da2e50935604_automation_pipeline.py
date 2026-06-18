"""automation_pipeline

Revision ID: da2e50935604
Revises: 7fed40f71a71
Create Date: 2026-06-18 10:02:17.749000+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'da2e50935604'
down_revision: str | None = '7fed40f71a71'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_PREV_STATUSES = (
    "UPLOADED", "PROCESSING", "PROCESSED", "SECTIONING", "SECTIONED",
    "CHUNKING", "CHUNKED", "EMBEDDING", "EMBEDDED", "EXTRACTING", "EXTRACTED",
    "COMPARING", "COMPARED", "ANALYZING", "ANALYZED",
    "RISK_EXTRACTING", "RISK_EXTRACTED",
    "TONE_EXTRACTING", "TONE_EXTRACTED", "FAILED",
)

_NEW_STATUSES = (
    "UPLOADED", "PROCESSING", "PROCESSED", "SECTIONING", "SECTIONED",
    "CHUNKING", "CHUNKED", "EMBEDDING", "EMBEDDED",
    "EXTRACTING", "EXTRACTED", "METRICS_EXTRACTING", "METRICS_READY",
    "COMPARING", "COMPARED", "COMPARISON_READY",
    "ANALYZING", "ANALYZED", "ANALYTICS", "ANALYTICS_READY",
    "RISK_EXTRACTING", "RISK_EXTRACTED", "RISKS", "RISKS_READY",
    "TONE_EXTRACTING", "TONE_EXTRACTED", "TONE", "READY", "FAILED",
)


def _in_list(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


def _status_check(values: tuple[str, ...]) -> str:
    return "status IN " + _in_list(values)


def upgrade() -> None:
    # 1. Drop existing constraints
    op.execute("ALTER TABLE reports DROP CONSTRAINT IF EXISTS ck_reports_report_status")
    op.execute("ALTER TABLE reports DROP CONSTRAINT IF EXISTS report_status")
    
    # 2. Alter status column length from 16 to 32
    op.alter_column('reports', 'status',
               existing_type=sa.String(length=16),
               type_=sa.String(length=32),
               existing_nullable=False)
               
    # 3. Re-create the check constraint report_status
    op.create_check_constraint("report_status", "reports", _status_check(_NEW_STATUSES))
    
    # 4. Add new metadata columns
    op.add_column('reports', sa.Column('failed_stage', sa.Text(), nullable=True))
    op.add_column('reports', sa.Column('completed_stage', sa.Text(), nullable=True))
    op.add_column('reports', sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    # 1. Drop added columns
    op.drop_column('reports', 'retry_count')
    op.drop_column('reports', 'completed_stage')
    op.drop_column('reports', 'failed_stage')
    
    # 2. Revert newly introduced statuses to FAILED
    op.execute(
        "UPDATE reports SET status = 'FAILED' "
        "WHERE status NOT IN " + _in_list(_PREV_STATUSES)
    )
    
    # 3. Drop constraints
    op.execute("ALTER TABLE reports DROP CONSTRAINT IF EXISTS ck_reports_report_status")
    op.execute("ALTER TABLE reports DROP CONSTRAINT IF EXISTS report_status")
    
    # 4. Revert status column length from 32 to 16
    op.alter_column('reports', 'status',
               existing_type=sa.String(length=32),
               type_=sa.String(length=16),
               existing_nullable=False)
               
    # 5. Re-create previous constraint
    op.create_check_constraint("report_status", "reports", _status_check(_PREV_STATUSES))
