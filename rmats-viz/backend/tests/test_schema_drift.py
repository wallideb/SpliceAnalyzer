"""Regression tests for the model ⇄ migration drift fixed in revision 0018.

No database needed: the checks inspect the ORM metadata and the Alembic
script directory.  (The authoritative check is ``alembic check`` against a
migrated PostgreSQL, run in CI / by hand.)

Run:  python -m pytest tests/test_schema_drift.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.database import Base  # noqa: E402
from app.models import analysis, deep_analysis, event, splice  # noqa: E402,F401  # register models


def _script_dir() -> ScriptDirectory:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    return ScriptDirectory.from_config(cfg)


def test_single_migration_head_is_0018():
    heads = _script_dir().get_heads()
    assert heads == ["0018"], heads


def test_0018_revises_0017():
    rev = _script_dir().get_revision("0018")
    assert rev.down_revision == "0017"


@pytest.mark.parametrize(
    "table, column, timezone",
    [
        ("analyses", "created_at", True),
        ("analyses", "updated_at", True),
        ("deep_analyses", "created_at", False),   # 0006 created a naive TIMESTAMP
        ("event_splice_feature", "computed_at", True),
    ],
)
def test_timestamp_columns_match_migrations(table, column, timezone):
    col = Base.metadata.tables[table].columns[column]
    assert col.nullable is False, f"{table}.{column} must be NOT NULL (0018)"
    assert bool(getattr(col.type, "timezone", False)) is timezone, (
        f"{table}.{column} timezone flag must match the migration that created it"
    )
    assert col.server_default is not None, f"{table}.{column} keeps its now() server default"


@pytest.mark.parametrize(
    "table, index, columns",
    [
        ("deep_analyses", "ix_deep_analyses_analysis_id", ["analysis_id"]),
        ("deep_analysis_events", "ix_dae_event_id", ["event_id"]),
        ("deep_analysis_events", "ix_dae_deep_analysis_id", ["deep_analysis_id"]),
        ("deep_analysis_events", "ix_dae_da_sig", ["deep_analysis_id", "is_significant"]),
    ],
)
def test_fk_indexes_declared_on_models(table, index, columns):
    """Indexes created by 0010 / 0011 / 0013 must exist on the ORM metadata,
    otherwise autogenerate proposes dropping them."""
    idx = {i.name: [c.name for c in i.columns] for i in Base.metadata.tables[table].indexes}
    assert idx.get(index) == columns, idx
