import uuid
from sqlalchemy import (
    String, Text, BigInteger, Integer, Double, ForeignKey,
    UniqueConstraint, Index, Computed
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class SplicingEvent(Base):
    __tablename__ = "splicing_events"
    __table_args__ = (
        UniqueConstraint(
            "analysis_id", "event_type", "gene_id", "chr", "strand",
            "exon_start", "exon_end", "upstream_es", "upstream_ee",
            "downstream_es", "downstream_ee",
            name="uq_splicing_event_identity",
        ),
        Index("ix_events_analysis_fdr", "analysis_id", "fdr"),
        Index("ix_events_analysis_type", "analysis_id", "event_type"),
        Index("ix_events_analysis_gene", "analysis_id", "gene_symbol"),
        Index("ix_events_analysis_chr_pos", "analysis_id", "chr", "exon_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )

    # Identity
    event_type: Mapped[str] = mapped_column(String(10), nullable=False)
    rmats_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    gene_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    gene_symbol: Mapped[str | None] = mapped_column(Text, nullable=True)
    chr: Mapped[str | None] = mapped_column(String(30), nullable=True)
    strand: Mapped[str | None] = mapped_column(String(1), nullable=True)

    # Coordinates
    exon_start: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    exon_end: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    upstream_es: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    upstream_ee: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    downstream_es: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    downstream_ee: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # MXE-only
    second_exon_start: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    second_exon_end: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # A3SS / A5SS-only (alternative-site coordinates; exon_start/exon_end
    # mirror the long exon and the flanking exon is copied into
    # upstream_* or downstream_* according to genomic position)
    long_exon_start: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    long_exon_end: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    short_es: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    short_ee: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    flanking_es: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    flanking_ee: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Counts
    ijc_sample_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    sjc_sample_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    ijc_sample_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    sjc_sample_2: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Isoform lengths (needed to interpret JCEC counts) and counting mode
    inc_form_len: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skip_form_len: Mapped[int | None] = mapped_column(Integer, nullable=True)
    counting_mode: Mapped[str | None] = mapped_column(String(4), nullable=True)  # "JC" | "JCEC"

    # Stats
    p_value: Mapped[float | None] = mapped_column(Double, nullable=True)
    fdr: Mapped[float | None] = mapped_column(Double, nullable=True)
    inc_level_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    inc_level_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    inc_level_difference: Mapped[float | None] = mapped_column(Double, nullable=True)

    # Derived
    abs_inc_level_diff: Mapped[float | None] = mapped_column(
        Double,
        Computed("ABS(inc_level_difference)", persisted=True),
        nullable=True,
    )

    analysis: Mapped["Analysis"] = relationship("Analysis", back_populates="events")  # noqa: F821
