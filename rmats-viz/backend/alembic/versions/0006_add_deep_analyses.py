"""add deep_analyses and deep_analysis_events tables

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deep_analyses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("analysis_id", UUID(as_uuid=True), sa.ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ready"),
        sa.Column("fdr_threshold", sa.Double(), nullable=False, server_default="0.05"),
        sa.Column("pvalue_threshold", sa.Double(), nullable=True),
        sa.Column("delta_psi_min", sa.Double(), nullable=False, server_default="0.1"),
        sa.Column("modules", JSONB(), nullable=False, server_default="[]"),
        sa.Column("n_significant", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_not_significant", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("permutation_iterations", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        "deep_analysis_events",
        sa.Column("deep_analysis_id", UUID(as_uuid=True), sa.ForeignKey("deep_analyses.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("event_id", UUID(as_uuid=True), sa.ForeignKey("splicing_events.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("is_significant", sa.Boolean(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("deep_analysis_events")
    op.drop_table("deep_analyses")
