"""
MANE Select transcript mapping
================================
For each SE event, retrieves the MANE Select transcript for the gene,
maps the skipped exon to the CDS, and determines frame impact.

Strategy
--------
1. Query Ensembl REST /overlap/region to find transcripts overlapping the
   skipped exon.  Filter those flagged as MANE Select (``is_mane_select=1``).
2. Fetch exon/CDS structure for the MANE transcript via /lookup/id.
3. Compute frame_class:
     - non_coding : exon entirely in UTR or no CDS overlap
     - in_frame   : coding length % 3 == 0
     - frameshift : coding length % 3 != 0
     - partial    : exon partially overlaps CDS boundary

Results are cached in a SQLite file (one row per gene_id + transcript_id)
to avoid repeated Ensembl calls across analysis runs.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_ENSEMBL = "https://rest.ensembl.org"
_TIMEOUT = 10.0
_HEADERS = {"Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# SQLite cache helpers
# ---------------------------------------------------------------------------

def _db_conn() -> sqlite3.Connection:
    path = Path(settings.MANE_CACHE_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS mane_cache (
            gene_id TEXT NOT NULL,
            exon_start INTEGER NOT NULL,
            exon_end INTEGER NOT NULL,
            transcript_id TEXT,
            exon_rank INTEGER,
            frame_region TEXT,
            frame_class TEXT,
            cds_exon_length INTEGER,
            PRIMARY KEY (gene_id, exon_start, exon_end)
        )"""
    )
    conn.commit()
    return conn


def _cache_get(gene_id: str, exon_start: int, exon_end: int) -> dict | None:
    conn = _db_conn()
    row = conn.execute(
        "SELECT transcript_id, exon_rank, frame_region, frame_class, cds_exon_length"
        " FROM mane_cache WHERE gene_id=? AND exon_start=? AND exon_end=?",
        (gene_id, exon_start, exon_end),
    ).fetchone()
    conn.close()
    if row:
        return dict(zip(
            ["transcript_id", "exon_rank", "frame_region", "frame_class", "cds_exon_length"],
            row,
        ))
    return None


def _cache_set(gene_id: str, exon_start: int, exon_end: int, data: dict) -> None:
    conn = _db_conn()
    conn.execute(
        """INSERT OR REPLACE INTO mane_cache
           (gene_id, exon_start, exon_end, transcript_id,
            exon_rank, frame_region, frame_class, cds_exon_length)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            gene_id, exon_start, exon_end,
            data.get("transcript_id"),
            data.get("exon_rank"),
            data.get("frame_region"),
            data.get("frame_class"),
            data.get("cds_exon_length"),
        ),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Ensembl REST helpers (synchronous — used in background tasks)
# ---------------------------------------------------------------------------

def _ensembl_get(path: str) -> Any | None:
    try:
        resp = httpx.get(
            f"{_ENSEMBL}{path}",
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.debug("Ensembl %s → %d", path, resp.status_code)
    except Exception as exc:
        logger.debug("Ensembl request failed: %s", exc)
    return None


def _get_mane_transcript(chrom: str, exon_start: int, exon_end: int) -> str | None:
    """Return the MANE Select transcript ID overlapping the region, or None."""
    # Remove 'chr' prefix — Ensembl REST uses '19', not 'chr19'
    chrom_clean = chrom.lstrip("chr")
    data = _ensembl_get(
        f"/overlap/region/human/{chrom_clean}:{exon_start + 1}-{exon_end}"
        "?feature=transcript&content-type=application/json"
    )
    if not data:
        return None
    for t in data:
        if t.get("is_mane_select"):
            return t.get("id")
    return None


def _get_transcript_structure(transcript_id: str) -> dict | None:
    """Fetch exon list + CDS intervals for a transcript."""
    data = _ensembl_get(
        f"/lookup/id/{transcript_id}?expand=1&content-type=application/json"
    )
    return data


def _frame_class(
    exon_start: int,
    exon_end: int,
    transcript: dict,
) -> dict:
    """Compute frame_class, frame_region, cds_exon_length, exon_rank."""
    result: dict = {
        "frame_class": "unknown",
        "frame_region": "unknown",
        "cds_exon_length": None,
        "exon_rank": None,
    }

    exons = transcript.get("Exon", [])
    # Find exon rank (1-based)
    for idx, ex in enumerate(sorted(exons, key=lambda e: e.get("start", 0)), start=1):
        ex_s = ex.get("start", 0) - 1  # Ensembl 1-based → 0-based
        ex_e = ex.get("end", 0)
        # Near-match (within 10 bp) to handle edge cases
        if abs(ex_s - exon_start) <= 10 and abs(ex_e - exon_end) <= 10:
            result["exon_rank"] = idx
            break

    # CDS intervals
    cds_list = transcript.get("CDS", [])  # may be absent for non-coding
    if not cds_list:
        result["frame_region"] = "non_coding"
        result["frame_class"] = "non_coding"
        return result

    # Overall CDS span
    cds_starts = [c.get("start", 0) - 1 for c in cds_list]
    cds_ends   = [c.get("end", 0)     for c in cds_list]
    cds_start  = min(cds_starts)
    cds_end    = max(cds_ends)

    overlap_start = max(exon_start, cds_start)
    overlap_end   = min(exon_end,   cds_end)

    if overlap_start >= overlap_end:
        # No CDS overlap
        if exon_end <= cds_start:
            result["frame_region"] = "UTR5" if transcript.get("strand") == 1 else "UTR3"
        else:
            result["frame_region"] = "UTR3" if transcript.get("strand") == 1 else "UTR5"
        result["frame_class"] = "non_coding"
        return result

    cod_len = overlap_end - overlap_start

    # Partial CDS overlap?
    if overlap_start > exon_start or overlap_end < exon_end:
        result["frame_region"] = "partial"
    else:
        result["frame_region"] = "CDS"

    result["cds_exon_length"] = cod_len
    result["frame_class"] = "in_frame" if cod_len % 3 == 0 else "frameshift"
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def annotate_mane(
    gene_id: str,
    chrom: str,
    strand: str,
    exon_start: int,
    exon_end: int,
) -> dict:
    """Return MANE annotation dict for one SE event.

    Always returns a dict with keys:
    transcript_id, exon_rank, frame_region, frame_class, cds_exon_length
    (any value may be None on failure).
    """
    # Check cache first
    cached = _cache_get(gene_id, exon_start, exon_end)
    if cached is not None:
        return cached

    result: dict = {
        "transcript_id": None,
        "exon_rank": None,
        "frame_region": "unknown",
        "frame_class": "unknown",
        "cds_exon_length": None,
    }

    transcript_id = _get_mane_transcript(chrom, exon_start, exon_end)
    if not transcript_id:
        _cache_set(gene_id, exon_start, exon_end, result)
        return result

    result["transcript_id"] = transcript_id

    transcript = _get_transcript_structure(transcript_id)
    if not transcript:
        _cache_set(gene_id, exon_start, exon_end, result)
        return result

    fc = _frame_class(exon_start, exon_end, transcript)
    result.update(fc)

    _cache_set(gene_id, exon_start, exon_end, result)
    return result
