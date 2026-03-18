"""drop event_cluster table — clustering is handled entirely at ingestion

The event_cluster table and its associated indexes were created in migrations
0003 and 0012 but the feature was redundant with the ingestion-time overlap
deduplication (which uses an OR condition, strictly stronger than the AND
condition used by the Union-Find clustering).  The table was never used in
any query result visible to users.  Drop it to keep the schema in sync with
the ORM models.

Revision ID: 0014
Revises: 0013
Create Date: 2026-03-17
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_event_cluster_rep_event", table_name="event_cluster", if_exists=True)
    op.drop_index("ix_event_cluster_analysis", table_name="event_cluster", if_exists=True)
    op.drop_table("event_cluster")


def downgrade() -> None:
    op.create_table(
        "event_cluster",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("gene_symbol", sa.Text, nullable=True),
        sa.Column("chr", sa.String(30), nullable=True),
        sa.Column("strand", sa.String(1), nullable=True),
        sa.Column("exon_start", sa.BigInteger, nullable=True),
        sa.Column("exon_end", sa.BigInteger, nullable=True),
        sa.Column("n_events", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "source_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "rep_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("splicing_events.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "analysis_id", "chr", "strand", "exon_start", "exon_end",
            name="uq_event_cluster_identity",
        ),
    )
    op.create_index("ix_event_cluster_analysis", "event_cluster", ["analysis_id"])
    op.create_index("ix_event_cluster_rep_event", "event_cluster", ["rep_event_id"])
