"""add sequence_source to event_splice_feature

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "event_splice_feature",
        sa.Column("sequence_source", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("event_splice_feature", "sequence_source")
