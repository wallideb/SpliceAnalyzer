"""add upstream_donor_is_gt and downstream_acceptor_is_ag columns

Revision ID: 0009
Revises: 0008
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "event_splice_feature",
        sa.Column("upstream_donor_is_gt", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "event_splice_feature",
        sa.Column("downstream_acceptor_is_ag", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("event_splice_feature", "downstream_acceptor_is_ag")
    op.drop_column("event_splice_feature", "upstream_donor_is_gt")
