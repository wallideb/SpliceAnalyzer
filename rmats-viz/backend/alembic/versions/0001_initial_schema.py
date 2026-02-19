"""initial schema

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="processing"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "sample_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("group_label", sa.Text(), nullable=False),
        sa.Column("group_index", sa.Integer(), nullable=False),
        sa.Column("sample_names", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_id", "group_index"),
    )

    op.create_table(
        "splicing_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(10), nullable=False),
        sa.Column("rmats_id", sa.BigInteger(), nullable=True),
        sa.Column("gene_id", sa.Text(), nullable=True),
        sa.Column("gene_symbol", sa.Text(), nullable=True),
        sa.Column("chr", sa.String(30), nullable=True),
        sa.Column("strand", sa.String(1), nullable=True),
        sa.Column("exon_start", sa.BigInteger(), nullable=True),
        sa.Column("exon_end", sa.BigInteger(), nullable=True),
        sa.Column("upstream_es", sa.BigInteger(), nullable=True),
        sa.Column("upstream_ee", sa.BigInteger(), nullable=True),
        sa.Column("downstream_es", sa.BigInteger(), nullable=True),
        sa.Column("downstream_ee", sa.BigInteger(), nullable=True),
        sa.Column("second_exon_start", sa.BigInteger(), nullable=True),
        sa.Column("second_exon_end", sa.BigInteger(), nullable=True),
        sa.Column("ijc_sample_1", sa.Text(), nullable=True),
        sa.Column("sjc_sample_1", sa.Text(), nullable=True),
        sa.Column("ijc_sample_2", sa.Text(), nullable=True),
        sa.Column("sjc_sample_2", sa.Text(), nullable=True),
        sa.Column("p_value", sa.Double(), nullable=True),
        sa.Column("fdr", sa.Double(), nullable=True),
        sa.Column("inc_level_1", sa.Text(), nullable=True),
        sa.Column("inc_level_2", sa.Text(), nullable=True),
        sa.Column("inc_level_difference", sa.Double(), nullable=True),
        sa.Column(
            "abs_inc_level_diff",
            sa.Double(),
            sa.Computed("ABS(inc_level_difference)", persisted=True),
            nullable=True,
        ),
        sa.Column("top_rank", sa.Integer(), nullable=True),
        sa.CheckConstraint("top_rank BETWEEN 1 AND 10", name="ck_top_rank_range"),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "analysis_id", "event_type", "gene_id", "chr", "strand",
            "exon_start", "exon_end", "upstream_es", "upstream_ee",
            "downstream_es", "downstream_ee",
            name="uq_splicing_event_identity",
        ),
    )

    op.create_index("ix_events_analysis_fdr", "splicing_events", ["analysis_id", "fdr"])
    op.create_index("ix_events_analysis_type", "splicing_events", ["analysis_id", "event_type"])
    op.create_index("ix_events_analysis_gene", "splicing_events", ["analysis_id", "gene_symbol"])
    op.create_index(
        "ix_events_analysis_top_rank",
        "splicing_events",
        ["analysis_id", "top_rank"],
        postgresql_where=sa.text("top_rank IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("splicing_events")
    op.drop_table("sample_groups")
    op.drop_table("analyses")
