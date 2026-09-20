"""
Core rMATS parser: detect event type, parse TSV, deduplicate, bulk-insert.

Event type and counting mode (JC / JCEC) are read from the filename
(``<TYPE>.MATS.<JC|JCEC>.txt`` or ``fromGTF[.novel*].<TYPE>.txt``); when
the filename is uninformative the header is sniffed.

Deduplication is type-aware:
- SE: events sharing at least one boundary (exon start OR exon end) within
  ±``overlap_bp`` are collapsed to the one with the lowest FDR.
- RI: both boundaries of the retained-intron exon must be within
  ±``overlap_bp`` (AND rule).
- MXE: all four boundaries (first AND second exon start/end) must be within
  ±``overlap_bp``; a different second exon is a distinct event.
- A3SS / A5SS: only exact duplicates of the full
  (long exon, short exon, flanking exon) tuple are collapsed (typically the
  JC and JCEC versions of the same event); alternative sites a few nt apart
  (NAGNAG…) are genuine distinct events and are kept.

Handles the real PCBP1 file quirks:
- Extra non-standard columns (e.g. InPanelApp) → ignored
- Duplicate 'ID' column → pandas auto-renames to 'ID.1' → handled
- FDR=0 (extremely significant events) → valid
- Comma-separated IncLevel* values → stored as text
"""
from __future__ import annotations

import bisect
import io
import logging
import re
import uuid
from collections.abc import Iterable
from typing import Any

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import SplicingEvent
from app.utils.composite_key import (
    ALT_SITE_COORD_COLS,
    RAW_COL_MAP,
    REQUIRED_COLS,
    REQUIRED_COLS_BY_TYPE,
)

logger = logging.getLogger(__name__)

EVENT_TYPES: tuple[str, ...] = ("SE", "MXE", "A3SS", "A5SS", "RI")

# ``<TYPE>.MATS.<JC|JCEC>`` with the type token delimited on the left (start of
# name or a non-alphanumeric character) and the mode token delimited on the
# right, so that ``PRIMARY_SE.MATS.JC.txt`` → SE, ``MYSERIES_SE.MATS.JC.txt`` →
# SE (the old substring test returned RI for both), and browser/OS copies such
# as ``SE.MATS.JC (1).txt``, ``RI.MATS.JC - Copie.txt``, ``A3SS.MATS.JCEC.txt.gz``
# or ``SE_MATS_JC.txt`` are still recognised.
_MATS_FILE_RE = re.compile(
    r"(?:^|[^A-Za-z0-9])(SE|MXE|A3SS|A5SS|RI)[._-]MATS[._-](JC|JCEC)(?![A-Za-z0-9])", re.I
)
# ``fromGTF.<TYPE>.txt``, ``fromGTF.novelJunction.<TYPE>.txt``,
# ``fromGTF.novelSpliceSite.<TYPE>.txt`` (and legacy ``fromGTF.novelEvents.<TYPE>.txt``)
_FROM_GTF_RE = re.compile(
    r"(?:^|[^A-Za-z0-9])fromGTF[._](?:(?:novelJunction|novelSpliceSite|novelEvents)[._])?"
    r"(SE|MXE|A3SS|A5SS|RI)(?![A-Za-z0-9])",
    re.I,
)
# Loose fallback: a delimited type token anywhere in the name (``results_A5SS.txt``).
# Only used together with the header (see ``detect_event_type``) so that a
# stray ``RI``/``SE`` token can never override an unambiguous header.
_TYPE_TOKEN_RE = re.compile(r"(?:^|[^A-Za-z0-9])(SE|MXE|A3SS|A5SS|RI)(?![A-Za-z0-9])", re.I)
_MODE_TOKEN_RE = re.compile(r"(?:^|[^A-Za-z0-9])(JC|JCEC)(?![A-Za-z0-9])", re.I)

# Raw header columns that identify an event type unambiguously
_HEADER_RI = {"riExonStart_0base", "riExonStart", "riExonEnd"}
_HEADER_MXE = {"1stExonStart_0base", "1stExonStart", "1stExonEnd",
               "2ndExonStart_0base", "2ndExonStart", "2ndExonEnd"}
_HEADER_ALT_SITE = {"longExonStart_0base", "longExonStart", "longExonEnd",
                    "shortES", "shortEE", "flankingES", "flankingEE"}
_HEADER_SE = {"exonStart_0base", "exonStart", "exonEnd"}

_GENERIC_COORD_COLS = ("exon_start", "exon_end", "upstream_es", "upstream_ee",
                       "downstream_es", "downstream_ee")
_COUNT_COLS = ("ijc_sample_1", "sjc_sample_1", "ijc_sample_2", "sjc_sample_2")


# ---------------------------------------------------------------------------
# Event type / counting mode detection
# ---------------------------------------------------------------------------


def detect_event_type(filename: str, header_columns: Iterable[str] | None = None) -> str | None:
    """Infer the rMATS event type from the filename, optionally helped by the header.

    1. ``<TYPE>.MATS.<JC|JCEC>`` or ``fromGTF[.novel*].<TYPE>`` in the name
       (any prefix/suffix, case-insensitive) → that type.
    2. Otherwise, when *header_columns* is given: an unambiguous header
       (``riExonStart_0base`` → RI, ``1stExonStart_0base`` → MXE,
       ``exonStart_0base`` → SE) wins; an A3SS/A5SS header (``longExonStart_0base``)
       is resolved with a delimited ``A3SS``/``A5SS`` token in the name.
    3. Otherwise a delimited type token anywhere in the name (``results_A5SS.txt``).

    Returns one of SE, MXE, A3SS, A5SS, RI or ``None``.
    """
    name = (filename or "").strip()
    m = _MATS_FILE_RE.search(name)
    if m:
        return m.group(1).upper()
    m = _FROM_GTF_RE.search(name)
    if m:
        return m.group(1).upper()

    tokens = [t.upper() for t in _TYPE_TOKEN_RE.findall(name)]
    if header_columns is not None:
        cols = {str(c).strip() for c in header_columns}
        if cols & _HEADER_RI:
            return "RI"
        if cols & _HEADER_MXE:
            return "MXE"
        if cols & _HEADER_ALT_SITE:
            alt = [t for t in tokens if t in ("A3SS", "A5SS")]
            if alt:
                return alt[-1]
            logger.warning(
                "%s: header is A3SS/A5SS but the name carries no A3SS/A5SS token; "
                "rename the file (e.g. A3SS.MATS.JC.txt) to import it", name,
            )
            return None
        if cols & _HEADER_SE:
            return "SE"
    if tokens:
        logger.info("%s: event type %s inferred from a loose filename token", name, tokens[-1])
        return tokens[-1]
    return None


def detect_counting_mode(filename: str) -> str | None:
    """Return the rMATS counting mode encoded in the filename: ``"JC"``,
    ``"JCEC"`` or ``None`` (e.g. ``fromGTF.*`` annotation files)."""
    name = (filename or "").strip()
    m = _MATS_FILE_RE.search(name)
    if m:
        return m.group(2).upper()
    modes = [t.upper() for t in _MODE_TOKEN_RE.findall(name)]
    return modes[-1] if modes else None


def detect_event_type_from_header(columns: Iterable[str]) -> str | None:
    """Infer the event type from the raw rMATS header columns.

    ``riExonStart_0base`` → RI, ``1stExonStart_0base`` / ``2ndExonStart_0base``
    → MXE, ``exonStart_0base`` → SE.  A3SS and A5SS files share the same
    header (``longExonStart_0base`` …) and cannot be told apart, so ``None``
    is returned for them (the filename is required).
    """
    cols = {str(c).strip() for c in columns}
    if cols & _HEADER_RI:
        return "RI"
    if cols & _HEADER_MXE:
        return "MXE"
    if cols & _HEADER_ALT_SITE:
        logger.warning(
            "Header matches A3SS/A5SS but the two types cannot be distinguished "
            "from the header alone; the filename must contain the event type"
        )
        return None
    if cols & _HEADER_SE:
        return "SE"
    return None


def _read_header(content: bytes) -> list[str]:
    """Return the tab-separated column names of the first line of *content*."""
    first_line = content.split(b"\n", 1)[0]
    text = first_line.decode("utf-8", errors="replace").lstrip("﻿").rstrip("\r")
    return [c.strip() for c in text.split("\t")]


# ---------------------------------------------------------------------------
# Column normalisation
# ---------------------------------------------------------------------------


def _rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rename raw rMATS columns to internal names.
    - Drops columns not in RAW_COL_MAP.
    - Handles pandas auto-renaming duplicate 'ID' → 'ID.1' by dropping 'ID.1'.
    """
    # Drop pandas-renamed duplicate ID column if present
    if "ID.1" in df.columns:
        df = df.drop(columns=["ID.1"])

    rename_map: dict[str, str] = {}
    for col in df.columns:
        if col in RAW_COL_MAP:
            rename_map[col] = RAW_COL_MAP[col]

    df = df.rename(columns=rename_map)

    # Keep only columns we know about (first occurrence wins if two raw
    # columns map to the same internal name)
    known = set(RAW_COL_MAP.values())
    df = df[[c for c in df.columns if c in known]]
    df = df.loc[:, ~df.columns.duplicated()]
    return df


# ---------------------------------------------------------------------------
# Coverage filter
# ---------------------------------------------------------------------------


def _parse_count_list(value: Any) -> list[int | None]:
    """Split a comma-separated rMATS count cell into ints (``None`` for
    NA / unparseable replicate entries).  A missing cell gives ``[]``."""
    if value is None or (isinstance(value, float) and pd.isna(value)) or value is pd.NA:
        return []
    out: list[int | None] = []
    for token in str(value).split(","):
        token = token.strip()
        if not token:
            continue
        try:
            out.append(int(float(token)))
        except (ValueError, TypeError):
            out.append(None)
    return out


def filter_low_coverage(df: pd.DataFrame, min_coverage: int = 10) -> pd.DataFrame:
    """Drop events where the mean per-replicate coverage (IJC+SJC) over the
    *available* replicates is < *min_coverage* in either sample group.

    Per replicate, coverage = IJC + SJC.  Replicates whose IJC or SJC entry is
    NA / unparseable are ignored; when IJC and SJC list different numbers of
    replicates only the first ``min(len)`` pairs are used (logged).  Rows
    where a group has no parseable replicate at all are dropped
    (``missing_counts``).  If the four count columns are absent entirely the
    DataFrame is returned unchanged (annotation-only files).

    The returned frame carries ``attrs["n_dropped_low_coverage"]`` and
    ``attrs["n_dropped_missing_counts"]``.
    """
    if not set(_COUNT_COLS).issubset(df.columns):
        logger.info("Coverage filter skipped: count columns absent (annotation-only input)")
        df.attrs["n_dropped_low_coverage"] = 0
        df.attrs["n_dropped_missing_counts"] = 0
        return df

    n_unequal = 0

    def _row_mean(ijc_val: Any, sjc_val: Any) -> float:
        nonlocal n_unequal
        ijc_vals = _parse_count_list(ijc_val)
        sjc_vals = _parse_count_list(sjc_val)
        if ijc_vals and sjc_vals and len(ijc_vals) != len(sjc_vals):
            n_unequal += 1
        cov = [i + s for i, s in zip(ijc_vals, sjc_vals) if i is not None and s is not None]
        if not cov:
            return float("nan")
        return sum(cov) / len(cov)

    def _mean_coverage(ijc_col: str, sjc_col: str) -> pd.Series:
        return pd.Series(
            [_row_mean(i, s) for i, s in zip(df[ijc_col], df[sjc_col])],
            index=df.index,
            dtype="float64",
        )

    mean_cov_1 = _mean_coverage("ijc_sample_1", "sjc_sample_1")
    mean_cov_2 = _mean_coverage("ijc_sample_2", "sjc_sample_2")

    missing = mean_cov_1.isna() | mean_cov_2.isna()
    low = ~missing & ((mean_cov_1 < min_coverage) | (mean_cov_2 < min_coverage))
    mask = ~missing & ~low

    before = len(df)
    result = df[mask].reset_index(drop=True)
    n_missing = int(missing.sum())
    n_low = int(low.sum())
    result.attrs["n_dropped_low_coverage"] = n_low
    result.attrs["n_dropped_missing_counts"] = n_missing

    if n_unequal:
        logger.warning(
            "Coverage filter: %d rows have unequal IJC/SJC replicate counts; "
            "only the paired replicates were used", n_unequal,
        )
    if n_missing or n_low:
        logger.info(
            "Coverage filter (>=%dX): dropped %d / %d events "
            "(%d low coverage, %d missing/unparseable counts)",
            min_coverage, n_missing + n_low, before, n_low, n_missing,
        )
    return result


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce coordinate and stat columns to appropriate numeric types."""
    coord_cols = [
        "exon_start", "exon_end", "upstream_es", "upstream_ee",
        "downstream_es", "downstream_ee", "second_exon_start", "second_exon_end",
        "long_exon_start", "long_exon_end", "short_es", "short_ee",
        "flanking_es", "flanking_ee", "inc_form_len", "skip_form_len", "rmats_id",
    ]
    float_cols = ["p_value", "fdr", "inc_level_difference"]

    for col in coord_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    for col in float_cols:
        if col in df.columns:
            # Handle French locale decimal comma (e.g. "-0,117" → "-0.117")
            df[col] = df[col].astype(str).str.replace(",", ".", regex=False)
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def _derive_alt_site_generic_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Fill the generic coordinate columns for A3SS / A5SS rows.

    ``exon_start`` / ``exon_end`` mirror the long exon.  The flanking exon is
    placed in ``upstream_*`` when it lies at lower genomic coordinates
    (``flanking_ee <= long_exon_start``), otherwise in ``downstream_*``; the
    other pair is left null.  This keeps the downstream code (Manhattan plot,
    sequence windows, identity constraint) working on alternative-site events.
    """
    for col in ALT_SITE_COORD_COLS:
        if col not in df.columns:
            df[col] = pd.Series([pd.NA] * len(df), index=df.index, dtype="Int64")

    na_col = pd.Series([pd.NA] * len(df), index=df.index, dtype="Int64")

    df["exon_start"] = df["long_exon_start"]
    df["exon_end"] = df["long_exon_end"]

    is_upstream = (df["flanking_ee"] <= df["long_exon_start"]).fillna(False).astype(bool)
    is_downstream = (df["flanking_ee"] > df["long_exon_start"]).fillna(False).astype(bool)

    df["upstream_es"] = df["flanking_es"].where(is_upstream, na_col)
    df["upstream_ee"] = df["flanking_ee"].where(is_upstream, na_col)
    df["downstream_es"] = df["flanking_es"].where(is_downstream, na_col)
    df["downstream_ee"] = df["flanking_ee"].where(is_downstream, na_col)
    return df


def parse_rmats_file(
    content: bytes,
    event_type: str,
    analysis_id: uuid.UUID,
    counting_mode: str | None = None,
) -> pd.DataFrame:
    """
    Parse a single rMATS TSV file.

    Returns a DataFrame with normalised column names and analysis_id /
    event_type (and counting_mode when known) set.  Rows whose type-specific
    coordinate columns are all null are dropped.  For A3SS / A5SS the generic
    ``exon_*`` / ``upstream_*`` / ``downstream_*`` columns are derived from
    the long and flanking exons.
    """
    if not content.strip():
        logger.warning("Empty file for event type %s", event_type)
        return pd.DataFrame()

    try:
        df = pd.read_csv(
            io.BytesIO(content),
            sep="\t",
            na_values=["NA", "nan", ""],
            dtype=str,  # read everything as str first, coerce later
        )
    except pd.errors.EmptyDataError:
        # No columns to parse (zero-byte or whitespace-only payload).
        logger.warning("Empty file for event type %s", event_type)
        return pd.DataFrame()

    if df.empty:
        logger.warning("Empty file for event type %s", event_type)
        return pd.DataFrame()

    df = _rename_columns(df)
    df = _coerce_types(df)

    # Drop rows missing all type-specific coordinate columns
    required = REQUIRED_COLS_BY_TYPE.get(event_type, frozenset(REQUIRED_COLS))
    coord_cols_present = [c for c in required if c in df.columns]
    if coord_cols_present:
        before = len(df)
        df = df.dropna(subset=coord_cols_present, how="all")
        dropped = before - len(df)
        if dropped:
            logger.warning("Dropped %d rows with null coordinates (%s)", dropped, event_type)
    else:
        logger.warning(
            "No %s coordinate column found in file (expected one of %s)",
            event_type, sorted(required),
        )

    if event_type in ("A3SS", "A5SS"):
        df = _derive_alt_site_generic_columns(df)

    df["event_type"] = event_type
    df["analysis_id"] = str(analysis_id)
    if counting_mode:
        df["counting_mode"] = counting_mode

    # Computed derived column (will also be stored as a generated column in DB)
    if "inc_level_difference" in df.columns:
        df["abs_inc_level_diff"] = df["inc_level_difference"].abs()

    logger.info("Parsed %d rows for event type %s", len(df), event_type)
    return df


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def _int_or_none(v: Any) -> int | None:
    """Convert a pandas scalar (Int64 / float / NA) to ``int`` or ``None``."""
    if v is None or v is pd.NA:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return int(v)


def _col_list(group_df: pd.DataFrame, col: str) -> list[int | None]:
    """Column values of *group_df* as Python ints / ``None``."""
    if col not in group_df.columns:
        return [None] * len(group_df)
    return [_int_or_none(v) for v in group_df[col].tolist()]


def _has_neighbour(sorted_vals: list[int], value: int | None, overlap_bp: int) -> bool:
    """True when *sorted_vals* holds a value within ±*overlap_bp* of *value*."""
    if value is None or not sorted_vals:
        return False
    pos = bisect.bisect_left(sorted_vals, value)
    if pos < len(sorted_vals) and sorted_vals[pos] - value <= overlap_bp:
        return True
    if pos > 0 and value - sorted_vals[pos - 1] <= overlap_bp:
        return True
    return False


def _dedup_se_group(
    starts: list[int | None], ends: list[int | None], overlap_bp: int
) -> list[int]:
    """SE rule: a candidate is a duplicate when any kept event has its start
    within ±overlap_bp OR its end within ±overlap_bp.  Rows are assumed sorted
    by priority (best first).  Returns positions of kept rows.

    Because the two conditions are independent, two sorted lists of kept
    starts and kept ends suffice (bisect → O(n log n))."""
    kept: list[int] = []
    kept_starts: list[int] = []
    kept_ends: list[int] = []
    for i, (s, e) in enumerate(zip(starts, ends)):
        if _has_neighbour(kept_starts, s, overlap_bp) or _has_neighbour(kept_ends, e, overlap_bp):
            continue
        kept.append(i)
        if s is not None:
            bisect.insort(kept_starts, s)
        if e is not None:
            bisect.insort(kept_ends, e)
    return kept


def _dedup_and_group(boundaries: list[list[int | None]], overlap_bp: int) -> list[int]:
    """AND rule (RI: exon start/end; MXE: first AND second exon start/end):
    a candidate is a duplicate only when a kept event has EVERY boundary in
    *boundaries* within ±overlap_bp.  Rows with any null boundary are always
    kept and never used as a reference.  Kept tuples are held sorted by their
    first boundary so only candidates within that window are inspected."""
    kept: list[int] = []
    kept_tuples: list[tuple[int, ...]] = []  # sorted by first boundary
    kept_firsts: list[int] = []
    for i, key in enumerate(zip(*boundaries)):
        if any(v is None for v in key):
            kept.append(i)
            continue
        first = key[0]
        is_dup = False
        if kept_firsts:
            lo = bisect.bisect_left(kept_firsts, first - overlap_bp)
            hi = bisect.bisect_right(kept_firsts, first + overlap_bp)
            for kt in kept_tuples[lo:hi]:
                if all(abs(v - kv) <= overlap_bp for v, kv in zip(key, kt)):
                    is_dup = True
                    break
        if is_dup:
            continue
        kept.append(i)
        pos = bisect.bisect_right(kept_firsts, first)
        kept_firsts.insert(pos, first)
        kept_tuples.insert(pos, tuple(key))  # type: ignore[arg-type]
    return kept


def _dedup_exact_group(cols: list[list[int | None]]) -> list[int]:
    """A3SS / A5SS rule: collapse exact duplicates of the full coordinate
    tuple only (first occurrence, i.e. lowest FDR, is kept)."""
    kept: list[int] = []
    seen: set[tuple[int | None, ...]] = set()
    for i, key in enumerate(zip(*cols)):
        if key in seen:
            continue
        seen.add(key)
        kept.append(i)
    return kept


def deduplicate_with_overlap(df: pd.DataFrame, overlap_bp: int = 50) -> pd.DataFrame:
    """
    Type-aware deduplication, retaining the lowest-FDR event of each cluster
    (ties broken by largest |ΔΨ|).

    Within each (event_type, gene_id, chr, strand) group, events are processed
    in order of increasing FDR (NaN last):

    - SE: near-duplicate when ``|exon_start − kept_start| ≤ overlap_bp`` OR
      ``|exon_end − kept_end| ≤ overlap_bp``.
    - RI: near-duplicate only when BOTH boundaries of the retained intron
      exon are within ``overlap_bp``.
    - MXE: near-duplicate only when all four boundaries (first AND second
      exon start/end) are within ``overlap_bp``; a different second exon is
      a distinct event.
    - A3SS / A5SS: only exact duplicates of
      (long_exon_start, long_exon_end, short_es, short_ee, flanking_es,
      flanking_ee) are collapsed (JC vs JCEC merge); alternative sites a few
      nt apart are kept.

    The returned frame carries ``attrs["n_collapsed_by_type"]``.
    """
    if df.empty:
        df.attrs["n_collapsed_by_type"] = {}
        return df

    # Sort by FDR ASC (lowest first), NaN last, then |ΔΨ| DESC
    sort_cols = [c for c in ("fdr", "abs_inc_level_diff") if c in df.columns]
    if sort_cols:
        df = df.sort_values(
            by=sort_cols,
            ascending=[c == "fdr" for c in sort_cols],
            na_position="last",
        )
    df = df.reset_index(drop=True)

    group_cols = [c for c in ["event_type", "gene_id", "chr", "strand"] if c in df.columns]
    kept_indices: list[int] = []
    n_collapsed_by_type: dict[str, int] = {}
    alt_cols = ["long_exon_start", "long_exon_end", "short_es", "short_ee",
                "flanking_es", "flanking_ee"]

    groups = df.groupby(group_cols, sort=False, dropna=False) if group_cols else [(None, df)]
    for _, group_df in groups:
        event_type = (
            str(group_df["event_type"].iloc[0]) if "event_type" in group_df.columns else ""
        )
        if event_type == "SE":
            kept_pos = _dedup_se_group(
                _col_list(group_df, "exon_start"), _col_list(group_df, "exon_end"), overlap_bp
            )
        elif event_type == "RI":
            kept_pos = _dedup_and_group(
                [_col_list(group_df, "exon_start"), _col_list(group_df, "exon_end")], overlap_bp
            )
        elif event_type == "MXE":
            kept_pos = _dedup_and_group(
                [_col_list(group_df, c) for c in
                 ("exon_start", "exon_end", "second_exon_start", "second_exon_end")],
                overlap_bp,
            )
        elif event_type in ("A3SS", "A5SS"):
            kept_pos = _dedup_exact_group([_col_list(group_df, c) for c in alt_cols])
        else:
            kept_pos = _dedup_exact_group([_col_list(group_df, c) for c in _GENERIC_COORD_COLS])

        idx = group_df.index
        kept_indices.extend(int(idx[p]) for p in kept_pos)
        collapsed = len(group_df) - len(kept_pos)
        if collapsed:
            n_collapsed_by_type[event_type] = n_collapsed_by_type.get(event_type, 0) + collapsed

    kept_indices.sort()
    result = df.loc[kept_indices].reset_index(drop=True)
    result.attrs["n_collapsed_by_type"] = n_collapsed_by_type
    logger.info(
        "After type-aware deduplication (±%d bp SE / AND RI,MXE / exact A3SS,A5SS): "
        "%d rows (from %d); collapsed by type: %s",
        overlap_bp, len(result), len(df), n_collapsed_by_type or "{}",
    )
    return result


# ---------------------------------------------------------------------------
# Bulk insert
# ---------------------------------------------------------------------------


def _df_to_records(df: pd.DataFrame, analysis_id: uuid.UUID) -> list[dict[str, Any]]:
    """Convert DataFrame to a list of dicts suitable for bulk insert.

    Uses pandas vectorized operations instead of iterrows() for a 10-50× speedup
    on large DataFrames (100k+ rows).
    """
    columns = [
        c.name for c in SplicingEvent.__table__.columns
        if c.name not in ("id", "abs_inc_level_diff", "analysis_id")
    ]
    # Keep only columns that exist in the DataFrame
    present_cols = [c for c in columns if c in df.columns]
    sub = df[present_cols]

    # Replace pandas NA/NaT/NaN with None (vectorised)
    sub = sub.astype(object).where(sub.notna(), other=None)

    # Convert numpy scalars → Python natives via to_dict("records")
    # (pandas already does this for most dtypes when orient="records")
    raw_records: list[dict] = sub.to_dict("records")

    # Convert any remaining numpy scalars (int64/float64) that survived
    records: list[dict[str, Any]] = []
    for rec in raw_records:
        out: dict[str, Any] = {"id": uuid.uuid4(), "analysis_id": analysis_id}
        for k, v in rec.items():
            if hasattr(v, "item"):   # numpy scalar
                v = v.item()
            out[k] = v
        records.append(out)
    return records


async def parse_and_store(
    files: list[tuple[str, bytes]],
    analysis_id: uuid.UUID,
    db: AsyncSession,
) -> int:
    """
    Parse all uploaded files, coverage-filter, deduplicate, bulk-insert.

    Returns the number of rows actually inserted (rows skipped by the
    identity unique constraint are not counted).
    """
    all_dfs: list[pd.DataFrame] = []
    n_parsed = 0

    for filename, content in files:
        if not content.strip():
            logger.warning("File %s is empty, skipped", filename)
            continue
        event_type = detect_event_type(filename)
        counting_mode = detect_counting_mode(filename)
        if event_type is None:
            # Header-assisted detection (loose filename token + header family)
            event_type = detect_event_type(filename, _read_header(content))
            if event_type is None:
                logger.warning(
                    "Cannot infer event type from filename or header: %s — skipping", filename
                )
                continue
            logger.info("Event type %s inferred from header for %s", event_type, filename)
        parsed = parse_rmats_file(content, event_type, analysis_id, counting_mode=counting_mode)
        if not parsed.empty:
            n_parsed += len(parsed)
            all_dfs.append(parsed)

    if not all_dfs:
        logger.warning("No valid events parsed for analysis %s", analysis_id)
        return 0

    combined = pd.concat(all_dfs, ignore_index=True)
    filtered = filter_low_coverage(combined, min_coverage=10)
    n_dropped_low = int(filtered.attrs.get("n_dropped_low_coverage", 0))
    n_dropped_missing = int(filtered.attrs.get("n_dropped_missing_counts", 0))
    deduped = deduplicate_with_overlap(filtered, overlap_bp=50)
    n_collapsed_by_type: dict[str, int] = dict(deduped.attrs.get("n_collapsed_by_type", {}))
    n_collapsed = sum(n_collapsed_by_type.values())

    records = _df_to_records(deduped, analysis_id)

    n_inserted = 0
    if records:
        # PostgreSQL has a ~32 767 parameter limit per statement.
        # With ~35 columns per row, batches of 500 stay well within limits.
        BATCH_SIZE = 500
        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i : i + BATCH_SIZE]
            stmt = (
                insert(SplicingEvent)
                .values(batch)
                .on_conflict_do_nothing(constraint="uq_splicing_event_identity")
                .returning(SplicingEvent.id)
            )
            result = await db.execute(stmt)
            n_inserted += len(result.scalars().all())
        await db.flush()

    logger.info(
        "Analysis %s: %d rows parsed, %d dropped (missing counts), %d dropped (low coverage), "
        "%d collapsed by dedup (%s), %d attempted, %d inserted, %d skipped as identity conflicts",
        analysis_id, n_parsed, n_dropped_missing, n_dropped_low,
        n_collapsed, n_collapsed_by_type or "{}",
        len(records), n_inserted, len(records) - n_inserted,
    )
    return n_inserted
