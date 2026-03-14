"""add missing FK indexes on deep_analyses.analysis_id and deep_analysis_events.event_id

Both columns are FK targets in the cascade chain but had no index, causing full
table scans during CASCADE DELETE.  The explicit deletion order in _do_delete
avoids relying on these, but the indexes are still needed for correctness and
for other queries that filter by these columns.

Revision ID: 0013
Revises: 0012
Create Date: 2026-03-14
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_deep_analyses_analysis_id", "deep_analyses", ["analysis_id"])
    op.create_index("ix_dae_event_id", "deep_analysis_events", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_dae_event_id", table_name="deep_analysis_events")
    op.drop_index("ix_deep_analyses_analysis_id", table_name="deep_analyses")
