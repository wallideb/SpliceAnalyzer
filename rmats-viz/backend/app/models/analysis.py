import uuid
from datetime import datetime
from sqlalchemy import String, Text, Integer, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="processing")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    mutated_genes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    sample_groups: Mapped[list["SampleGroup"]] = relationship(
        "SampleGroup", back_populates="analysis", cascade="all, delete-orphan"
    )
    events: Mapped[list["SplicingEvent"]] = relationship(  # noqa: F821
        "SplicingEvent", back_populates="analysis", cascade="all, delete-orphan"
    )


class SampleGroup(Base):
    __tablename__ = "sample_groups"
    __table_args__ = (UniqueConstraint("analysis_id", "group_index"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("analyses.id", ondelete="CASCADE"))
    group_label: Mapped[str] = mapped_column(Text, nullable=False)
    group_index: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_names: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    analysis: Mapped["Analysis"] = relationship("Analysis", back_populates="sample_groups")
