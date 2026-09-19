"""make the server-defaulted timestamp columns NOT NULL

The ORM models declare ``analyses.created_at`` / ``updated_at``,
``deep_analyses.created_at`` and ``event_splice_feature.computed_at`` as
non-nullable (every response schema requires them and ``updated_at`` is the
splice-compute heartbeat), but migrations 0001 / 0003 / 0006 created them
without a NOT NULL constraint, so ``alembic check`` reported drift.  All four
columns have a ``now()`` server default; any NULL left by an explicit insert is
back-filled before the constraint is added.

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

_COLUMNS: tuple[tuple[str, str, sa.types.TypeEngine], ...] = (
    ("analyses", "created_at", sa.DateTime(timezone=True)),
    ("analyses", "updated_at", sa.DateTime(timezone=True)),
    ("deep_analyses", "created_at", sa.DateTime()),
    ("event_splice_feature", "computed_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    for table, column, col_type in _COLUMNS:
        op.execute(f"UPDATE {table} SET {column} = now() WHERE {column} IS NULL")
        op.alter_column(table, column, existing_type=col_type, nullable=False,
                        existing_server_default=sa.text("now()"))


def downgrade() -> None:
    for table, column, col_type in reversed(_COLUMNS):
        op.alter_column(table, column, existing_type=col_type, nullable=True,
                        existing_server_default=sa.text("now()"))
