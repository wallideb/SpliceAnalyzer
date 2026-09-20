from __future__ import annotations

import fcntl
import json
import logging
import os
import re
import shutil
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile, status,
)
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import AsyncSessionLocal, get_db
from app.models.analysis import Analysis, SampleGroup
from app.models.deep_analysis import DeepAnalysis, DeepAnalysisEvent
from app.models.event import SplicingEvent
from app.models.splice import EventSpliceFeature
from app.schemas.analysis import AnalysisListItem, AnalysisResponse, UploadResponse
from app.services.parser import parse_and_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analyses", tags=["analyses"])


async def _do_delete(analysis_id: uuid.UUID) -> None:
    """Delete an analysis by explicitly removing each child table in dependency order.

    We do NOT rely on PostgreSQL's implicit CASCADE chain (triggered by a single
    DELETE on the parent row) because that mechanism scans FK-target columns
    row-by-row — any missing index on those columns causes O(n×m) full-table
    scans that hang for minutes on large datasets.

    Instead every statement here deletes by analysis_id (always indexed) or by
    a single subquery that resolves to analysis_id in one hop.  Each step is
    logged so the exact point of failure is immediately visible.

    On any failure (including asyncio.CancelledError from a container restart)
    the status is reset to 'error' so the user can retry.
    """
    logger.info("DELETE /analyses/%s — background deletion starting", analysis_id)
    try:
        async with AsyncSessionLocal() as db:
            # 1. Delete deep_analysis_events (FK → deep_analyses AND splicing_events).
            #    Resolved via deep_analyses.analysis_id (one-hop subquery).
            da_subq = select(DeepAnalysis.id).where(DeepAnalysis.analysis_id == analysis_id)
            r = await db.execute(
                delete(DeepAnalysisEvent).where(DeepAnalysisEvent.deep_analysis_id.in_(da_subq))
            )
            logger.info("DELETE /analyses/%s — deleted %d deep_analysis_events", analysis_id, r.rowcount)

            # 2. Delete event_splice_feature (FK → splicing_events).
            #    Resolved via splicing_events.analysis_id (one-hop subquery).
            ev_subq = select(SplicingEvent.id).where(SplicingEvent.analysis_id == analysis_id)
            r = await db.execute(
                delete(EventSpliceFeature).where(EventSpliceFeature.event_id.in_(ev_subq))
            )
            logger.info("DELETE /analyses/%s — deleted %d event_splice_features", analysis_id, r.rowcount)

            # 3. Delete deep_analyses (direct analysis_id FK; deep_analysis_events already gone).
            r = await db.execute(
                delete(DeepAnalysis).where(DeepAnalysis.analysis_id == analysis_id)
            )
            logger.info("DELETE /analyses/%s — deleted %d deep_analyses", analysis_id, r.rowcount)

            # 4. Delete splicing_events (direct analysis_id FK; all dependents already gone).
            r = await db.execute(
                delete(SplicingEvent).where(SplicingEvent.analysis_id == analysis_id)
            )
            logger.info("DELETE /analyses/%s — deleted %d splicing_events", analysis_id, r.rowcount)

            # 5. Delete sample_groups (direct analysis_id FK).
            r = await db.execute(
                delete(SampleGroup).where(SampleGroup.analysis_id == analysis_id)
            )
            logger.info("DELETE /analyses/%s — deleted %d sample_groups", analysis_id, r.rowcount)

            # 6. Delete the analysis itself (all dependents gone; CASCADE finds nothing).
            r = await db.execute(
                delete(Analysis).where(Analysis.id == analysis_id)
            )
            logger.info("DELETE /analyses/%s — deleted analysis row (found=%d)", analysis_id, r.rowcount)

            await db.commit()
        logger.info("DELETE /analyses/%s — done", analysis_id)
    except BaseException:
        logger.exception("DELETE /analyses/%s — background deletion failed", analysis_id)
        # Reset status so the user can retry (don't leave it stuck as 'deleting').
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(Analysis)
                    .where(Analysis.id == analysis_id)
                    .values(status="error", error_message="Deletion failed — please retry")
                )
                await db.commit()
        except Exception:
            logger.exception("DELETE /analyses/%s — failed to reset status after error", analysis_id)
        raise


async def _create_analysis_from_files(
    name: str,
    group1_label: str,
    group2_label: str,
    group1_samples_json: str,
    group2_samples_json: str,
    mutated_genes_json: str,
    file_data: list[tuple[str, bytes]],
    db: AsyncSession,
) -> UploadResponse:
    """Create an analysis from already-read file contents.

    Shared by the single-shot multipart endpoint (``POST /analyses``) and the
    chunked-upload finalizer (``POST /analyses/uploads/{id}/finalize``): the
    analysis row is created with status 'processing', the files are parsed
    synchronously (status → 'ready'), and a parser failure is recorded on the
    row ('error' + error_message) before being re-raised as HTTP 500.
    """
    analysis_id = uuid.uuid4()
    try:
        parsed_genes = json.loads(mutated_genes_json)
        if not isinstance(parsed_genes, list):
            parsed_genes = []
    except json.JSONDecodeError:
        parsed_genes = []
    analysis = Analysis(id=analysis_id, name=name, status="processing", mutated_genes=parsed_genes)
    db.add(analysis)

    try:
        g1_samples = json.loads(group1_samples_json)
        g2_samples = json.loads(group2_samples_json)
    except json.JSONDecodeError:
        g1_samples, g2_samples = [], []

    db.add(SampleGroup(analysis_id=analysis_id, group_label=group1_label, group_index=1, sample_names=g1_samples))
    db.add(SampleGroup(analysis_id=analysis_id, group_label=group2_label, group_index=2, sample_names=g2_samples))
    await db.flush()

    # Parsing runs synchronously inside the request (status 'processing' →
    # 'ready').  The analysis row is created first so a parser failure can be
    # recorded on it ('error' + error_message) and surfaced by GET /analyses/{id}.
    #
    # TODO(ingestion stats): parse_and_store() returns only the inserted row
    # count.  The parser records per-file drop reasons on the DataFrame
    # (df.attrs["n_dropped_low_coverage"], ["n_dropped_missing_counts"],
    # ["n_collapsed_by_type"]) but those frames are internal to the service;
    # exposing n_rows_read / n_dropped_* / n_collapsed in UploadResponse
    # requires parse_and_store to return a stats object.  Until then only
    # coarse warnings derived from the returned count are reported.
    warnings: list[str] = []
    try:
        for fname, payload in file_data:
            if not payload.strip():
                warnings.append(f"File '{fname}' is empty, skipped")
        event_count = await parse_and_store(file_data, analysis_id, db)
        analysis.status = "ready"
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.exception("Failed to parse analysis %s", analysis_id)
        async with AsyncSessionLocal() as err_db:
            err_analysis = await err_db.get(Analysis, analysis_id)
            if err_analysis:
                err_analysis.status = "error"
                err_analysis.error_message = f"Parser error: {exc}"
            else:
                err_db.add(Analysis(
                    id=analysis_id, name=name, status="error",
                    error_message=f"Parser error: {exc}", mutated_genes=parsed_genes,
                ))
            await err_db.commit()
        raise HTTPException(status_code=500, detail=f"Parser error: {exc}") from exc

    if event_count == 0:
        warnings.append(
            "No events were imported: check that the files are rMATS *.MATS.JC(EC).txt "
            "outputs and that events pass the coverage filter (mean ≥ 10 reads per group)"
        )

    return UploadResponse(
        analysis_id=analysis_id, status="ready", event_count=event_count, warnings=warnings,
    )


@router.post("", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def create_analysis(
    name: str = Form(...),
    group1_label: str = Form("Subjects"),
    group2_label: str = Form("Controls"),
    group1_samples: str = Form("[]"),
    group2_samples: str = Form("[]"),
    mutated_genes: str = Form("[]"),
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Single-shot multipart upload (curl / API clients).

    Browsers use the chunked path below instead, because reverse proxies
    commonly cap request bodies at ~1 MB (HTTP 413).
    """
    file_data = [(f.filename or f"file_{i}", await f.read()) for i, f in enumerate(files)]
    return await _create_analysis_from_files(
        name, group1_label, group2_label, group1_samples, group2_samples, mutated_genes, file_data, db,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Chunked upload sessions
# ═══════════════════════════════════════════════════════════════════════════
#
# Proxies in front of the API (GitHub Codespaces port forwarding, a default
# nginx ``client_max_body_size``) reject request bodies above ~1 MB, so the
# browser cannot POST a 10–100 MB rMATS file in one multipart request.  The
# client therefore opens a session, PUTs each file as a sequence of small raw
# chunks (the frontend uses 512 KB) and finalizes with the analysis metadata.
#
# All state lives on the filesystem under UPLOAD_TMP_DIR/<upload_id>/:
#   meta.json          {"created_at": ..., "files": {<name>: {received_chunks,
#                       total_chunks, received_bytes}}}  (written atomically)
#   <name>.part        the chunks appended in order
#   .lock              flock() target serialising chunk appends per session
# so several Uvicorn workers on one host share sessions without any process
# memory, and a crashed session is simply purged after UPLOAD_SESSION_TTL_HOURS.

MAX_CHUNK_BYTES = 4 * 1024 * 1024  # 4 MiB — anything larger is a client bug (413)
_UPLOAD_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_FILENAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_META = "meta.json"
_LOCK = ".lock"


class ChunkOrderError(ValueError):
    """Raised when a chunk arrives out of sequence; ``expected`` is the index wanted."""

    def __init__(self, expected: int, index: int):
        super().__init__(f"Chunk index {index} out of order: expected {expected}")
        self.expected = expected
        self.index = index


def sanitize_upload_filename(name: str) -> str:
    """Return the basename of ``name`` if it only uses ``[A-Za-z0-9._-]``.

    Any directory component (``/`` or ``\\``) is stripped first so a client
    that sends a full path still works; the result is rejected (ValueError)
    when it is empty, ``.``/``..`` or contains a disallowed character, which
    also rules out every path-traversal trick.
    """
    base = os.path.basename(name.replace("\\", "/"))
    if not base or base in {".", ".."} or not _FILENAME_RE.fullmatch(base):
        raise ValueError(
            f"Invalid filename {name!r}: only [A-Za-z0-9._-] characters are allowed"
        )
    return base


def chunk_is_new(index: int, received: int, total: int) -> bool:
    """Sequential-order rule for one file of an upload session.

    ``received`` chunks (``0 … received-1``) are already on disk.  The next
    chunk must be exactly ``received`` (→ True: append it).  Resending the
    last chunk received (``index == received - 1``) is the idempotent retry a
    client performs after a lost response (→ False: acknowledge, do not
    append).  Anything else is out of order → ``ChunkOrderError``; an index
    outside ``[0, total)`` or a file already complete is a ``ValueError``.
    """
    if index < 0 or index >= total:
        raise ValueError(f"Chunk index {index} outside [0, {total})")
    if index == received:
        if received >= total:
            raise ValueError(f"File already complete ({total} chunks)")
        return True
    if index == received - 1:
        return False
    raise ChunkOrderError(expected=received, index=index)


def _upload_root() -> Path:
    return Path(settings.UPLOAD_TMP_DIR)


def _session_dir(upload_id: str) -> Path:
    """Directory of an existing session, or HTTP 404."""
    if not _UPLOAD_ID_RE.fullmatch(upload_id):
        raise HTTPException(status_code=404, detail="Upload session not found")
    d = _upload_root() / upload_id
    if not d.is_dir() or not (d / _META).is_file():
        raise HTTPException(status_code=404, detail="Upload session not found")
    return d


def _read_meta(d: Path) -> dict:
    with open(d / _META, encoding="utf-8") as fh:
        return json.load(fh)


def _write_meta(d: Path, meta: dict) -> None:
    """Atomic replace: readers never see a half-written meta.json."""
    tmp = d / f"{_META}.{uuid.uuid4().hex}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(meta, fh)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, d / _META)


@contextmanager
def _session_lock(d: Path) -> Iterator[None]:
    """Serialise read-modify-write of one session across requests / workers."""
    with open(d / _LOCK, "a+") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _purge_stale_sessions(now: datetime | None = None) -> int:
    """Delete session directories older than UPLOAD_SESSION_TTL_HOURS (best effort)."""
    root = _upload_root()
    if not root.is_dir():
        return 0
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=settings.UPLOAD_SESSION_TTL_HOURS)
    purged = 0
    for d in root.iterdir():
        try:
            if not d.is_dir() or not _UPLOAD_ID_RE.fullmatch(d.name):
                continue
            try:
                created = datetime.fromisoformat(_read_meta(d)["created_at"])
            except Exception:
                created = datetime.fromtimestamp(d.stat().st_mtime, tz=timezone.utc)
            if created < cutoff:
                shutil.rmtree(d, ignore_errors=True)
                purged += 1
        except Exception:  # pragma: no cover — best effort only
            logger.warning("Could not inspect upload session %s", d, exc_info=True)
    if purged:
        logger.info("Purged %d stale upload session(s) older than %dh", purged, settings.UPLOAD_SESSION_TTL_HOURS)
    return purged


@router.post("/uploads", status_code=status.HTTP_201_CREATED)
async def create_upload_session():
    """Open a chunked-upload session → ``{"upload_id": "<uuid>"}``."""
    root = _upload_root()
    root.mkdir(parents=True, exist_ok=True)
    try:
        _purge_stale_sessions()
    except Exception:  # pragma: no cover
        logger.warning("Stale upload session purge failed", exc_info=True)
    upload_id = str(uuid.uuid4())
    d = root / upload_id
    d.mkdir()
    _write_meta(d, {"created_at": datetime.now(timezone.utc).isoformat(), "files": {}})
    return {"upload_id": upload_id}


@router.put("/uploads/{upload_id}/chunk")
async def upload_chunk(
    upload_id: str,
    request: Request,
    filename: str = Query(..., description="Basename of the file; [A-Za-z0-9._-] only"),
    index: int = Query(..., ge=0, description="0-based chunk index; must be sequential"),
    total: int = Query(..., ge=1, description="Total number of chunks for this file"),
):
    """Append one raw chunk (``Content-Type: application/octet-stream``) to a file.

    Chunks of a file must arrive in order: ``index`` has to equal the number
    already received (409 with ``expected`` otherwise).  Resending the last
    chunk received is acknowledged with 200 without appending, so a client can
    safely retry after a lost response.  Bodies above 4 MiB are rejected (413).
    """
    d = _session_dir(upload_id)
    try:
        fname = sanitize_upload_filename(filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    body = await request.body()
    if len(body) > MAX_CHUNK_BYTES:
        raise HTTPException(status_code=413, detail=f"Chunk larger than {MAX_CHUNK_BYTES} bytes")

    with _session_lock(d):
        meta = _read_meta(d)
        entry = meta["files"].get(fname) or {"received_chunks": 0, "total_chunks": total, "received_bytes": 0}
        if entry["total_chunks"] != total:
            raise HTTPException(
                status_code=422,
                detail=f"total={total} differs from the {entry['total_chunks']} announced for '{fname}'",
            )
        try:
            append = chunk_is_new(index, entry["received_chunks"], total)
        except ChunkOrderError as exc:
            raise HTTPException(
                status_code=409,
                detail={"message": str(exc), "filename": fname, "expected": exc.expected, "received": exc.index},
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        if append:
            with open(d / f"{fname}.part", "ab") as fh:
                fh.write(body)
            entry["received_chunks"] += 1
            entry["received_bytes"] += len(body)
            meta["files"][fname] = entry
            _write_meta(d, meta)

    return {
        "filename": fname,
        "received_chunks": entry["received_chunks"],
        "total_chunks": entry["total_chunks"],
        "received_bytes": entry["received_bytes"],
    }


@router.post("/uploads/{upload_id}/finalize", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def finalize_upload(
    upload_id: str,
    name: str = Form(...),
    group1_label: str = Form("Subjects"),
    group2_label: str = Form("Controls"),
    group1_samples: str = Form("[]"),
    group2_samples: str = Form("[]"),
    mutated_genes: str = Form("[]"),
    files: str = Form(..., description="JSON list of the uploaded filenames to import, in order"),
    db: AsyncSession = Depends(get_db),
):
    """Assemble the uploaded files and create the analysis (same result as ``POST /analyses``).

    Every listed file must be complete (409 otherwise).  The session directory
    is removed whether the import succeeds or fails.
    """
    d = _session_dir(upload_id)
    try:
        wanted = json.loads(files)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="'files' must be a JSON list of filenames") from exc
    if not isinstance(wanted, list) or not wanted or not all(isinstance(x, str) for x in wanted):
        raise HTTPException(status_code=422, detail="'files' must be a non-empty JSON list of filenames")
    try:
        wanted = [sanitize_upload_filename(x) for x in wanted]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        with _session_lock(d):
            meta = _read_meta(d)
            for fname in wanted:
                entry = meta["files"].get(fname)
                if entry is None:
                    raise HTTPException(status_code=409, detail=f"File '{fname}' was not uploaded in this session")
                if entry["received_chunks"] != entry["total_chunks"]:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"File '{fname}' is incomplete: {entry['received_chunks']}/{entry['total_chunks']} chunks received"
                        ),
                    )
            file_data = [(fname, (d / f"{fname}.part").read_bytes()) for fname in wanted]
        total_bytes = sum(len(b) for _, b in file_data)
        logger.info(
            "Finalizing chunked upload %s: %d file(s), %d bytes → analysis '%s'",
            upload_id, len(file_data), total_bytes, name,
        )
        return await _create_analysis_from_files(
            name, group1_label, group2_label, group1_samples, group2_samples, mutated_genes, file_data, db,
        )
    finally:
        shutil.rmtree(d, ignore_errors=True)


@router.delete("/uploads/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
async def abort_upload(upload_id: str):
    """Abort a session: remove its directory and every partial file."""
    d = _session_dir(upload_id)
    shutil.rmtree(d, ignore_errors=True)


@router.get("", response_model=list[AnalysisListItem])
async def list_analyses(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Analysis).order_by(Analysis.created_at.desc()))
    return result.scalars().all()


@router.get("/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis(analysis_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Analysis)
        .options(selectinload(Analysis.sample_groups))
        .where(Analysis.id == analysis_id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis


@router.delete("/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_analysis(
    analysis_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Verify existence, mark the analysis as 'deleting', return 204 immediately.

    The actual deletion runs as a background task (single CASCADE DELETE) so
    the browser never waits on the heavy work.  Marking status='deleting'
    prevents a second concurrent delete request from queuing a duplicate task.
    """
    result = await db.execute(select(Analysis.id, Analysis.status).where(Analysis.id == analysis_id))
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if row.status == "deleting":
        # Already in progress — return 204 without queuing a second task.
        return

    await db.execute(
        update(Analysis).where(Analysis.id == analysis_id).values(status="deleting")
    )
    await db.commit()

    logger.info("DELETE /analyses/%s — accepted, queuing background deletion", analysis_id)
    background_tasks.add_task(_do_delete, analysis_id)
