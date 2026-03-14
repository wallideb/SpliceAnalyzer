"""index event_cluster.rep_event_id to speed up CASCADE SET NULL on delete

Without this index, deleting an analysis triggers a full sequential scan of
event_cluster for every splicing_event row being deleted (to find SET NULL
targets).  With large datasets that is O(n*m) scans and takes minutes.

Revision ID: 0012
Revises: 0011
Create Date: 2026-03-14
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_event_cluster_rep_event",
        "event_cluster",
        ["rep_event_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_event_cluster_rep_event", table_name="event_cluster")
