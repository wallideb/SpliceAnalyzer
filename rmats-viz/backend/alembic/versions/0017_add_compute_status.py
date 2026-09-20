"""add compute_status / compute_error to analyses; bp_position / bp_motif to
event_splice_feature

1. Replaces the in-process ``_active_computes`` dict of the splice router with
   a persistent state so that progress polling and the export readiness check
   are correct with several uvicorn workers and after a crash of the
   background task.

       analyses.compute_status : 'idle' | 'running' | 'done' | 'error'  (default 'idle')
       analyses.compute_error  : last error message when compute_status = 'error'

2. Persists the branch-point match details computed by
   services/splice_features.find_branch_point:

       event_splice_feature.bp_position : 0-based index of the 7-mer in ppt_seq
       event_splice_feature.bp_motif    : the matched 7-mer

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

    op.add_column("event_splice_feature", sa.Column("bp_position", sa.Integer(), nullable=True))
    op.add_column("event_splice_feature", sa.Column("bp_motif", sa.String(7), nullable=True))


def downgrade() -> None:
    op.drop_column("event_splice_feature", "bp_motif")
    op.drop_column("event_splice_feature", "bp_position")

    op.drop_column("analyses", "compute_error")
    op.drop_column("analyses", "compute_status")
