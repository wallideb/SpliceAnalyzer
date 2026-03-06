"""add splice features tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── event_cluster ─────────────────────────────────────────────────────────
    # Groups rMATS SE events from the same gene whose exon boundaries are
    # within 50 bp of each other (|Δ5'| ≤ 50 AND |Δ3'| ≤ 50).
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
        # Median exon boundaries across cluster members
        sa.Column("exon_start", sa.BigInteger, nullable=True),
        sa.Column("exon_end", sa.BigInteger, nullable=True),
        sa.Column("n_events", sa.Integer, nullable=False, server_default="1"),
        # JSON list of splicing_event.id strings belonging to this cluster
        sa.Column(
            "source_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        # The representative event (lowest FDR)
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

    # ── event_splice_feature ──────────────────────────────────────────────────
    # One row per SE event: raw sequences + derived splice-signal features.
    op.create_table(
        "event_splice_feature",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("splicing_events.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        # ── sizes ──
        sa.Column("exon_size", sa.Integer, nullable=True),
        sa.Column("upstream_intron_size", sa.Integer, nullable=True),
        sa.Column("downstream_intron_size", sa.Integer, nullable=True),
        # ── raw sequences ──
        # Donor  : 3 nt exon + 6 nt intron  = 9 nt  (5'SS)
        sa.Column("donor_seq", sa.Text, nullable=True),
        # Acceptor: 20 nt intron + 3 nt exon = 23 nt (3'SS)
        sa.Column("acceptor_seq", sa.Text, nullable=True),
        # PPT zone: ~47 nt upstream of 3'SS (includes branch-point window)
        sa.Column("ppt_seq", sa.Text, nullable=True),
        # ── GT-AG rule ──
        sa.Column("donor_is_gt", sa.Boolean, nullable=True),
        sa.Column("acceptor_is_ag", sa.Boolean, nullable=True),
        # ── PPT metrics ──
        sa.Column("ppt_score", sa.Double(precision=53), nullable=True),      # fraction C+T
        sa.Column("ppt_longest_run", sa.Integer, nullable=True),              # longest Y-run
        # ── Branch-point (YNYURAY rule-based) ──
        sa.Column("bp_motif_found", sa.Boolean, nullable=True),
        sa.Column("bp_distance", sa.Integer, nullable=True),                  # nt from 3'SS
        sa.Column("bp_score", sa.Integer, nullable=True),                     # 0-7 match score
        # ── MANE / frame ──
        sa.Column("mane_transcript_id", sa.Text, nullable=True),
        sa.Column("exon_rank", sa.Integer, nullable=True),
        sa.Column("frame_region", sa.Text, nullable=True),   # CDS|UTR5|UTR3|partial|unknown
        sa.Column("frame_class", sa.Text, nullable=True),    # in_frame|frameshift|non_coding|unknown
        sa.Column("cds_exon_length", sa.Integer, nullable=True),
        sa.Column(
            "computed_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_event_splice_feature_event", "event_splice_feature", ["event_id"]
    )


def downgrade() -> None:
    op.drop_table("event_splice_feature")
    op.drop_table("event_cluster")
