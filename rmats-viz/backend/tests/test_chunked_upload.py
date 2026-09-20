"""Chunked upload sessions (``POST /analyses/uploads`` → PUT chunk → finalize).

No database: the endpoint tests run the FastAPI app in-process through
``httpx.ASGITransport`` and monkeypatch ``_create_analysis_from_files`` so the
finalizer's only observable effect is the ``file_data`` it hands over.  The
session root is redirected to a pytest tmp_path via ``settings.UPLOAD_TMP_DIR``.

Run:  python -m pytest tests/test_chunked_upload.py -q
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import analyses as mod  # noqa: E402
from app.schemas.analysis import UploadResponse  # noqa: E402


# ── pure functions ────────────────────────────────────────────────────────


@pytest.mark.parametrize("raw, expected", [
    ("SE.MATS.JC.txt", "SE.MATS.JC.txt"),
    ("/tmp/run1/SE.MATS.JCEC.txt", "SE.MATS.JCEC.txt"),          # directory stripped
    ("C:\\Users\\me\\A3SS.MATS.JC.txt", "A3SS.MATS.JC.txt"),     # Windows path stripped
    ("../../etc/passwd", "passwd"),                              # traversal → basename only
    ("a-b_c.1", "a-b_c.1"),
])
def test_sanitize_upload_filename_accepts_basenames(raw, expected):
    assert mod.sanitize_upload_filename(raw) == expected


@pytest.mark.parametrize("raw", ["", ".", "..", "dir/", "SE MATS.txt", "résumé.txt", "a;b", "x\ny", "a/../"])
def test_sanitize_upload_filename_rejects(raw):
    with pytest.raises(ValueError):
        mod.sanitize_upload_filename(raw)


def test_chunk_rule_sequential_append():
    assert mod.chunk_is_new(index=0, received=0, total=3) is True
    assert mod.chunk_is_new(index=1, received=1, total=3) is True
    assert mod.chunk_is_new(index=2, received=2, total=3) is True


def test_chunk_rule_resend_last_is_idempotent():
    assert mod.chunk_is_new(index=0, received=1, total=3) is False
    assert mod.chunk_is_new(index=2, received=3, total=3) is False  # after completion too


def test_chunk_rule_out_of_order_names_expected_index():
    with pytest.raises(mod.ChunkOrderError) as ei:
        mod.chunk_is_new(index=2, received=0, total=3)
    assert ei.value.expected == 0 and ei.value.index == 2
    with pytest.raises(mod.ChunkOrderError) as ei:   # going backwards more than one
        mod.chunk_is_new(index=0, received=2, total=3)
    assert ei.value.expected == 2


def test_chunk_rule_rejects_index_out_of_range_and_overflow():
    with pytest.raises(ValueError):
        mod.chunk_is_new(index=3, received=3, total=3)     # beyond total
    with pytest.raises(ValueError):
        mod.chunk_is_new(index=-1, received=0, total=3)
    with pytest.raises(ValueError):
        mod.chunk_is_new(index=1, received=1, total=1)     # would exceed a complete file


# ── endpoints (no DB) ─────────────────────────────────────────────────────

FORM = {
    "name": "chunked", "group1_label": "Patients", "group2_label": "Controls",
    "group1_samples": json.dumps(["P1"]), "group2_samples": json.dumps(["C1"]),
    "mutated_genes": json.dumps([{"symbol": "GENE1", "ensembl_id": "ENSG1", "display": "GENE1"}]),
}


@pytest.fixture
def upload_root(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_TMP_DIR", str(root))
    return root


@pytest.fixture
def captured(monkeypatch) -> dict:
    """Replace the DB-backed creator with a recorder returning a fixed UploadResponse."""
    calls: dict = {}

    async def fake_create(name, g1, g2, g1s, g2s, genes, file_data, db):
        calls.update(name=name, g1=g1, g2=g2, g1s=g1s, g2s=g2s, genes=genes, file_data=file_data)
        return UploadResponse(analysis_id=uuid.uuid4(), status="ready", event_count=7, warnings=["w"])

    monkeypatch.setattr(mod, "_create_analysis_from_files", fake_create)
    # The finalizer declares Depends(get_db); replace it so no engine is touched.
    from app.database import get_db

    async def no_db():
        yield None

    app.dependency_overrides[get_db] = no_db
    yield calls
    app.dependency_overrides.pop(get_db, None)


def run(coro):
    return asyncio.run(coro)


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def put_chunk(c: AsyncClient, uid: str, fname: str, idx: int, total: int, body: bytes):
    return await c.put(
        f"/api/v1/analyses/uploads/{uid}/chunk",
        params={"filename": fname, "index": idx, "total": total},
        content=body, headers={"Content-Type": "application/octet-stream"},
    )


def test_full_chunked_flow(upload_root, captured):
    async def scenario():
        async with await _client() as c:
            r = await c.post("/api/v1/analyses/uploads")
            assert r.status_code == 201, r.text
            uid = r.json()["upload_id"]
            uuid.UUID(uid)
            sdir = upload_root / uid
            assert (sdir / "meta.json").is_file()

            # three-chunk file (the last one is deliberately short), one-chunk file
            big = b"A" * 1000 + b"B" * 1000 + b"C" * 10
            parts = [big[0:1000], big[1000:2000], big[2000:]]
            small = b"tiny\n"

            for i, p in enumerate(parts):
                r = await put_chunk(c, uid, "SE.MATS.JC.txt", i, 3, p)
                assert r.status_code == 200, r.text
                assert r.json() == {"filename": "SE.MATS.JC.txt", "received_chunks": i + 1,
                                    "total_chunks": 3, "received_bytes": sum(len(x) for x in parts[: i + 1])}
            r = await put_chunk(c, uid, "summary.txt", 0, 1, small)
            assert r.status_code == 200 and r.json()["received_chunks"] == 1

            # progress is persisted in meta.json
            meta = json.loads((sdir / "meta.json").read_text())
            assert meta["files"]["SE.MATS.JC.txt"] == {"received_chunks": 3, "total_chunks": 3, "received_bytes": len(big)}
            assert (sdir / "SE.MATS.JC.txt.part").read_bytes() == big

            # out-of-order chunk for a new file → 409 with the expected index
            r = await put_chunk(c, uid, "RI.MATS.JC.txt", 1, 2, b"x")
            assert r.status_code == 409, r.text
            assert r.json()["detail"]["expected"] == 0 and r.json()["detail"]["filename"] == "RI.MATS.JC.txt"
            assert not (sdir / "RI.MATS.JC.txt.part").exists()

            # resending the last chunk of a complete file → 200, nothing appended
            r = await put_chunk(c, uid, "SE.MATS.JC.txt", 2, 3, parts[2])
            assert r.status_code == 200 and r.json()["received_chunks"] == 3 and r.json()["received_bytes"] == len(big)
            assert (sdir / "SE.MATS.JC.txt.part").read_bytes() == big

            # appending beyond the announced total → 422
            r = await put_chunk(c, uid, "SE.MATS.JC.txt", 3, 3, b"z")
            assert r.status_code == 422
            # changing the announced total → 422
            r = await put_chunk(c, uid, "summary.txt", 1, 5, b"z")
            assert r.status_code == 422

            # bad filename → 422 (chunk) — and the id/filename checks come before any write
            r = await put_chunk(c, uid, "SE MATS.txt", 0, 1, b"x")
            assert r.status_code == 422
            r = await put_chunk(c, uid, "..", 0, 1, b"x")
            assert r.status_code == 422

            # chunk bigger than 4 MiB → 413
            r = await put_chunk(c, uid, "huge.txt", 0, 1, b"\0" * (mod.MAX_CHUNK_BYTES + 1))
            assert r.status_code == 413

            # finalize
            r = await c.post(
                f"/api/v1/analyses/uploads/{uid}/finalize",
                data={**FORM, "files": json.dumps(["SE.MATS.JC.txt", "summary.txt"])},
            )
            assert r.status_code == 201, r.text
            body = r.json()
            assert body["status"] == "ready" and body["event_count"] == 7 and body["warnings"] == ["w"]
            assert captured["file_data"] == [("SE.MATS.JC.txt", big), ("summary.txt", small)]
            assert (captured["name"], captured["g1"], captured["g2"]) == ("chunked", "Patients", "Controls")
            assert captured["g1s"] == FORM["group1_samples"] and captured["genes"] == FORM["mutated_genes"]
            assert not sdir.exists()

            # the session is gone: every endpoint now answers 404
            assert (await c.post(f"/api/v1/analyses/uploads/{uid}/finalize", data={**FORM, "files": "[]"})).status_code == 404
            assert (await put_chunk(c, uid, "a.txt", 0, 1, b"x")).status_code == 404
            assert (await c.delete(f"/api/v1/analyses/uploads/{uid}")).status_code == 404

    run(scenario())


def test_unknown_upload_id_is_404(upload_root, captured):
    async def scenario():
        async with await _client() as c:
            unknown = str(uuid.uuid4())
            assert (await put_chunk(c, unknown, "a.txt", 0, 1, b"x")).status_code == 404
            assert (await c.post(f"/api/v1/analyses/uploads/{unknown}/finalize",
                                 data={**FORM, "files": json.dumps(["a.txt"])})).status_code == 404
            assert (await c.delete(f"/api/v1/analyses/uploads/{unknown}")).status_code == 404
            # malformed ids (path traversal attempts) are 404 too, never touching the disk
            assert (await put_chunk(c, "..", "a.txt", 0, 1, b"x")).status_code in (404, 405)
            assert (await c.delete("/api/v1/analyses/uploads/not-a-uuid")).status_code == 404
            assert "file_data" not in captured

    run(scenario())


def test_finalize_incomplete_or_missing_file_is_409_and_keeps_nothing(upload_root, captured):
    async def scenario():
        async with await _client() as c:
            uid = (await c.post("/api/v1/analyses/uploads")).json()["upload_id"]
            assert (await put_chunk(c, uid, "SE.MATS.JC.txt", 0, 2, b"half")).status_code == 200

            r = await c.post(f"/api/v1/analyses/uploads/{uid}/finalize",
                             data={**FORM, "files": json.dumps(["SE.MATS.JC.txt"])})
            assert r.status_code == 409, r.text
            assert "SE.MATS.JC.txt" in r.json()["detail"] and "1/2" in r.json()["detail"]
            assert "file_data" not in captured
            # the session directory is removed even when finalize fails
            assert not (upload_root / uid).exists()

            uid = (await c.post("/api/v1/analyses/uploads")).json()["upload_id"]
            r = await c.post(f"/api/v1/analyses/uploads/{uid}/finalize",
                             data={**FORM, "files": json.dumps(["never.txt"])})
            assert r.status_code == 409 and "never.txt" in r.json()["detail"]

            # 422s: bad JSON, empty list, bad filename in the list
            uid = (await c.post("/api/v1/analyses/uploads")).json()["upload_id"]
            for bad in ("not json", "[]", json.dumps(["a b.txt"]), json.dumps("x"), json.dumps([1])):
                r = await c.post(f"/api/v1/analyses/uploads/{uid}/finalize", data={**FORM, "files": bad})
                assert r.status_code == 422, (bad, r.text)
            assert "file_data" not in captured

    run(scenario())


def test_abort_removes_directory(upload_root, captured):
    async def scenario():
        async with await _client() as c:
            uid = (await c.post("/api/v1/analyses/uploads")).json()["upload_id"]
            assert (await put_chunk(c, uid, "a.txt", 0, 1, b"x")).status_code == 200
            assert (upload_root / uid / "a.txt.part").exists()
            r = await c.delete(f"/api/v1/analyses/uploads/{uid}")
            assert r.status_code == 204
            assert not (upload_root / uid).exists()

    run(scenario())


def test_stale_sessions_are_purged_on_create(upload_root, captured):
    async def scenario():
        async with await _client() as c:
            old = (await c.post("/api/v1/analyses/uploads")).json()["upload_id"]
            fresh = (await c.post("/api/v1/analyses/uploads")).json()["upload_id"]
            meta_path = upload_root / old / "meta.json"
            meta = json.loads(meta_path.read_text())
            meta["created_at"] = (datetime.now(timezone.utc) - timedelta(hours=settings.UPLOAD_SESSION_TTL_HOURS + 1)).isoformat()
            meta_path.write_text(json.dumps(meta))
            (upload_root / "not-a-session").mkdir()          # foreign entries are left alone
            (upload_root / "stray.txt").write_text("x")

            await c.post("/api/v1/analyses/uploads")
            assert not (upload_root / old).exists()
            assert (upload_root / fresh).exists()
            assert (upload_root / "not-a-session").exists() and (upload_root / "stray.txt").exists()

    run(scenario())


def test_empty_file_is_a_single_empty_chunk(upload_root, captured):
    """An empty rMATS file (e.g. summary.txt) is sent as one zero-byte chunk."""
    async def scenario():
        async with await _client() as c:
            uid = (await c.post("/api/v1/analyses/uploads")).json()["upload_id"]
            r = await put_chunk(c, uid, "summary.txt", 0, 1, b"")
            assert r.status_code == 200 and r.json()["received_bytes"] == 0
            r = await c.post(f"/api/v1/analyses/uploads/{uid}/finalize",
                             data={**FORM, "files": json.dumps(["summary.txt"])})
            assert r.status_code == 201
            assert captured["file_data"] == [("summary.txt", b"")]

    run(scenario())
