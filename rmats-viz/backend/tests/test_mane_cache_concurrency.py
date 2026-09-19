"""Regression test: concurrent first use of the MANE SQLite cache.

Eight worker threads (the annotation pool size) hit a fresh cache file at
once; before the fix one thread could DROP the table another had just
created ("no such table: mane_cache").
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.services import mane as mane_mod


@pytest.fixture
def fresh_cache(tmp_path, monkeypatch):
    db = tmp_path / "mane_cache.db"
    monkeypatch.setattr(settings, "MANE_CACHE_DB", str(db))
    mane_mod._schema_ready_for = None
    # drop any thread-local connection of the main thread
    if hasattr(mane_mod._local, "conn"):
        del mane_mod._local.conn
    yield db
    mane_mod._schema_ready_for = None


def _worker(i: int) -> dict | None:
    gene = f"ENSG{i:011d}"
    mane_mod._cache_set(gene, "+", 100 * i, 100 * i + 50, {
        "transcript_id": f"ENST{i:011d}", "exon_rank": 2,
        "frame_region": "CDS", "frame_class": "in_frame", "cds_exon_length": 50,
    })
    return mane_mod._cache_get(gene, "+", 100 * i, 100 * i + 50)


def test_concurrent_first_use_does_not_drop_table(fresh_cache):
    for _round in range(5):
        mane_mod._schema_ready_for = None
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(_worker, range(64)))
        assert all(r and r["frame_class"] == "in_frame" for r in results)


def test_old_schema_is_migrated_once(fresh_cache):
    import sqlite3
    conn = sqlite3.connect(str(fresh_cache))
    conn.execute("CREATE TABLE mane_cache (gene_id TEXT, exon_start INTEGER, exon_end INTEGER)")
    conn.commit(); conn.close()
    mane_mod._schema_ready_for = None
    mane_mod._cache_set("ENSG1", "-", 1, 2, {"transcript_id": "T", "frame_class": "in_frame"})
    assert mane_mod._cache_get("ENSG1", "-", 1, 2)["transcript_id"] == "T"
    cols = [r[1] for r in mane_mod._db_conn().execute("PRAGMA table_info(mane_cache)")]
    assert "strand" in cols
