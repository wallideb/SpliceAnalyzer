import uuid
from datetime import datetime
from sqlalchemy import (
    String, Text, Integer, BigInteger, Double, Boolean,
    ForeignKey, UniqueConstraint, Index, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class EventCluster(Base):
    """Canonical cluster of near-identical SE events (|Δexon_start| ≤ 50 bp
    AND |Δexon_end| ≤ 50 bp, same gene + strand)."""
    __tablename__ = "event_cluster"
    __table_args__ = (
        UniqueConstraint(
            "analysis_id", "chr", "strand", "exon_start", "exon_end",
            name="uq_event_cluster_identity",
        ),
        Index("ix_event_cluster_analysis", "analysis_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analyses.id", ondelete="CASCADE"),
        nullable=False,
    )
    gene_symbol: Mapped[str | None] = mapped_column(Text, nullable=True)
    chr: Mapped[str | None] = mapped_column(String(30), nullable=True)
    strand: Mapped[str | None] = mapped_column(String(1), nullable=True)
    exon_start: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    exon_end: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    n_events: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    rep_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("splicing_events.id", ondelete="SET NULL"),
        nullable=True,
    )


class EventSpliceFeature(Base):
    """Splice-signal features computed from local GRCh38 FASTA for one SE event."""
    __tablename__ = "event_splice_feature"
    __table_args__ = (
        Index("ix_event_splice_feature_event", "event_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("splicing_events.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # Sizes
    exon_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    upstream_intron_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    downstream_intron_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Raw sequences
    donor_seq: Mapped[str | None] = mapped_column(Text, nullable=True)    # 9 nt
    acceptor_seq: Mapped[str | None] = mapped_column(Text, nullable=True)  # 23 nt
    ppt_seq: Mapped[str | None] = mapped_column(Text, nullable=True)        # ~47 nt

    # GT-AG rule
    donor_is_gt: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    acceptor_is_ag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # PPT metrics
    ppt_score: Mapped[float | None] = mapped_column(Double(precision=53), nullable=True)
    ppt_longest_run: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Branch-point (YNYURAY rule)
    bp_motif_found: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    bp_distance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bp_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # MANE / frame annotation
    mane_transcript_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    exon_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frame_region: Mapped[str | None] = mapped_column(Text, nullable=True)
    frame_class: Mapped[str | None] = mapped_column(Text, nullable=True)
    cds_exon_length: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Source of sequence data: "fasta" | "ensembl" | None (sizes-only, no sequences)
    sequence_source: Mapped[str | None] = mapped_column(String(20), nullable=True)

    computed_at: Mapped[datetime] = mapped_column(server_default=func.now())
