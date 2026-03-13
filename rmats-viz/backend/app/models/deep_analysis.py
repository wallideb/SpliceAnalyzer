import uuid
from datetime import datetime
from sqlalchemy import (
    String, Text, Integer, Double, Boolean, ForeignKey, Index, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class DeepAnalysis(Base):
    """A saved deep-analysis run with threshold parameters and module selection."""

    __tablename__ = "deep_analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ready")

    # Significance thresholds used
    fdr_threshold: Mapped[float] = mapped_column(Double, nullable=False, default=0.05)
    pvalue_threshold: Mapped[float | None] = mapped_column(Double, nullable=True)
    delta_psi_min: Mapped[float] = mapped_column(Double, nullable=False, default=0.1)

    # Active optional modules
    modules: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Cached counts
    n_significant: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    n_not_significant: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Permutation config (filled when user runs a permutation)
    permutation_iterations: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Relationships
    analysis: Mapped["Analysis"] = relationship("Analysis", back_populates="deep_analyses")  # noqa: F821
    events: Mapped[list["DeepAnalysisEvent"]] = relationship(
        "DeepAnalysisEvent", back_populates="deep_analysis", cascade="all, delete-orphan",
    )


class DeepAnalysisEvent(Base):
    """Junction table linking events to a deep analysis with significance flag."""

    __tablename__ = "deep_analysis_events"
    __table_args__ = (
        # Simple index on deep_analysis_id for fast lookups by DA
        Index("ix_dae_deep_analysis_id", "deep_analysis_id"),
        # Composite index for queries that also filter by is_significant
        Index("ix_dae_da_sig", "deep_analysis_id", "is_significant"),
    )

    deep_analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deep_analyses.id", ondelete="CASCADE"), primary_key=True,
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("splicing_events.id", ondelete="CASCADE"), primary_key=True,
    )
    is_significant: Mapped[bool] = mapped_column(Boolean, nullable=False)

    deep_analysis: Mapped["DeepAnalysis"] = relationship("DeepAnalysis", back_populates="events")
    event: Mapped["SplicingEvent"] = relationship("SplicingEvent")  # noqa: F821
