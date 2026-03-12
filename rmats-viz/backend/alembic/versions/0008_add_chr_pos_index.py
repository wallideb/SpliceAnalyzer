"""add index on (analysis_id, chr, exon_start) for Manhattan plot queries

Revision ID: 0008
Revises: 0007
Create Date: 2026-03-11
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_events_analysis_chr_pos",
        "splicing_events",
        ["analysis_id", "chr", "exon_start"],
    )


def downgrade() -> None:
    op.drop_index("ix_events_analysis_chr_pos", table_name="splicing_events")
