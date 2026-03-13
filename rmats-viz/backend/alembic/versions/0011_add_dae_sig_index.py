"""add composite index on deep_analysis_events(deep_analysis_id, is_significant)

Revision ID: 0011
Revises: 0010
Create Date: 2026-03-13
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_dae_da_sig",
        "deep_analysis_events",
        ["deep_analysis_id", "is_significant"],
    )


def downgrade() -> None:
    op.drop_index("ix_dae_da_sig", table_name="deep_analysis_events")
