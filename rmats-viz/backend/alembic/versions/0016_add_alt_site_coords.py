"""add A3SS/A5SS alternative-site coordinates, isoform lengths, counting mode;
extend the event identity constraint

rMATS A3SS/A5SS files describe events with
  longExonStart_0base, longExonEnd, shortES, shortEE, flankingES, flankingEE
none of which were stored (rows lost their coordinates at import).

Also keeps IncFormLen / SkipFormLen (needed to interpret JCEC counts) and
records the counting mode ("JC" or "JCEC") the row was read from.

The identity constraint ``uq_splicing_event_identity`` is recreated (same
name) with the MXE second exon and the A3SS/A5SS long/short exon columns so
that events sharing only the generic coordinates are not silently dropped by
``ON CONFLICT DO NOTHING``.  NULLs are distinct in PostgreSQL unique
constraints, so nullable columns are fine.

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

_TABLE = "splicing_events"
_UQ = "uq_splicing_event_identity"

_BIGINT_COLS = (
    "long_exon_start",
    "long_exon_end",
    "short_es",
    "short_ee",
    "flanking_es",
    "flanking_ee",
)
_INT_COLS = ("inc_form_len", "skip_form_len")

_OLD_UQ_COLS = [
    "analysis_id", "event_type", "gene_id", "chr", "strand",
    "exon_start", "exon_end", "upstream_es", "upstream_ee",
    "downstream_es", "downstream_ee",
]
_NEW_UQ_COLS = _OLD_UQ_COLS + [
    "second_exon_start", "second_exon_end",
    "long_exon_start", "long_exon_end", "short_es", "short_ee",
]


def upgrade() -> None:
    for name in _BIGINT_COLS:
        op.add_column(_TABLE, sa.Column(name, sa.BigInteger(), nullable=True))
    for name in _INT_COLS:
        op.add_column(_TABLE, sa.Column(name, sa.Integer(), nullable=True))
    op.add_column(_TABLE, sa.Column("counting_mode", sa.String(4), nullable=True))

    op.drop_constraint(_UQ, _TABLE, type_="unique")
    op.create_unique_constraint(_UQ, _TABLE, _NEW_UQ_COLS)


def downgrade() -> None:
    op.drop_constraint(_UQ, _TABLE, type_="unique")
    op.create_unique_constraint(_UQ, _TABLE, _OLD_UQ_COLS)

    op.drop_column(_TABLE, "counting_mode")
    for name in reversed(_INT_COLS):
        op.drop_column(_TABLE, name)
    for name in reversed(_BIGINT_COLS):
        op.drop_column(_TABLE, name)
