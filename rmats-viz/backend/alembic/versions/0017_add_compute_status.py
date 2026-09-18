"""add compute_status / compute_error to analyses

Replaces the in-process ``_active_computes`` dict of the splice router with a
persistent state so that progress polling and the export readiness check are
correct with several uvicorn workers and after a crash of the background task.

    compute_status : 'idle' | 'running' | 'done' | 'error'  (default 'idle')
    compute_error  : last error message when compute_status = 'error'

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analyses",
        sa.Column("compute_status", sa.String(20), nullable=False, server_default="idle"),
    )
    op.add_column("analyses", sa.Column("compute_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("analyses", "compute_error")
    op.drop_column("analyses", "compute_status")
