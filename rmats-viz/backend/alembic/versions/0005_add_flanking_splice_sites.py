"""add upstream_donor_seq and downstream_acceptor_seq to event_splice_feature

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-07
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "event_splice_feature",
        sa.Column("upstream_donor_seq", sa.Text(), nullable=True),
    )
    op.add_column(
        "event_splice_feature",
        sa.Column("downstream_acceptor_seq", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("event_splice_feature", "downstream_acceptor_seq")
    op.drop_column("event_splice_feature", "upstream_donor_seq")
