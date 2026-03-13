"""add index on deep_analysis_events(deep_analysis_id)

Revision ID: 0010
Revises: 0009
Create Date: 2026-03-13
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_dae_deep_analysis_id",
        "deep_analysis_events",
        ["deep_analysis_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_dae_deep_analysis_id", table_name="deep_analysis_events")
