"""add mane_exon_source to event_splice_feature

Tracks how the MANE exon boundaries were determined:
  "overlap"  — reciprocal overlap matching
  "flanking" — fallback via flanking exon positions
  NULL       — no MANE correction applied

Revision ID: 0015
Revises: 0014
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "event_splice_feature",
        sa.Column("mane_exon_source", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("event_splice_feature", "mane_exon_source")
