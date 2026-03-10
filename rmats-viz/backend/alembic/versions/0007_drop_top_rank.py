"""drop top_rank column from splicing_events

Revision ID: 0007
Revises: 0006
Create Date: 2026-03-10
"""

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_events_analysis_top_rank", table_name="splicing_events")
    op.drop_constraint("ck_top_rank_range", table_name="splicing_events")
    op.drop_column("splicing_events", "top_rank")


def downgrade() -> None:
    op.add_column("splicing_events", sa.Column("top_rank", sa.Integer(), nullable=True))
    op.create_check_constraint("ck_top_rank_range", "splicing_events", "top_rank BETWEEN 1 AND 10")
    op.create_index(
        "ix_events_analysis_top_rank", "splicing_events",
        ["analysis_id", "top_rank"],
        postgresql_where="top_rank IS NOT NULL",
    )
