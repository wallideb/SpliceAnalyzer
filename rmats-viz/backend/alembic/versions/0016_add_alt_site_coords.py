"""add A3SS/A5SS alternative-site coordinates, isoform lengths and counting mode

rMATS A3SS/A5SS files describe events with
  longExonStart_0base, longExonEnd, shortES, shortEE, flankingES, flankingEE
none of which were stored (rows lost their coordinates at import).

Also keeps IncFormLen / SkipFormLen (needed to interpret JCEC counts) and
records the counting mode ("JC" or "JCEC") the row was read from.

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

_BIGINT_COLS = (
    "long_exon_start",
    "long_exon_end",
    "short_es",
    "short_ee",
    "flanking_es",
    "flanking_ee",
)
_INT_COLS = ("inc_form_len", "skip_form_len")


def upgrade() -> None:
    for name in _BIGINT_COLS:
        op.add_column(_TABLE, sa.Column(name, sa.BigInteger(), nullable=True))
    for name in _INT_COLS:
        op.add_column(_TABLE, sa.Column(name, sa.Integer(), nullable=True))
    op.add_column(_TABLE, sa.Column("counting_mode", sa.String(4), nullable=True))


def downgrade() -> None:
    op.drop_column(_TABLE, "counting_mode")
    for name in reversed(_INT_COLS):
        op.drop_column(_TABLE, name)
    for name in reversed(_BIGINT_COLS):
        op.drop_column(_TABLE, name)
