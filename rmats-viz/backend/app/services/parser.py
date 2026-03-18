"""
Core rMATS parser: detect event type, parse TSV, deduplicate, bulk-insert.

Handles the real PCBP1 file quirks:
- Extra non-standard columns (e.g. InPanelApp) → ignored
- Duplicate 'ID' column → pandas auto-renames to 'ID.1' → handled
- FDR=0 (extremely significant events) → valid
- Comma-separated IncLevel* values → stored as text
"""
from __future__ import annotations

import io
import logging
import uuid
from typing import Any

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import SplicingEvent
from app.utils.composite_key import RAW_COL_MAP, DEDUP_COLS_BY_TYPE, REQUIRED_COLS

logger = logging.getLogger(__name__)

EVENT_TYPE_KEYWORDS = ["SE", "RI", "A3SS", "A5SS", "MXE"]


def detect_event_type(filename: str) -> str | None:
    """Infer rMATS event type from filename (case-insensitive)."""
    upper = filename.upper()
    # MXE before SE to avoid false-positive match on 'SE' inside 'MXE' (not an issue here but safe)
    for et in ["MXE", "A3SS", "A5SS", "RI", "SE"]:
        if et in upper:
            return et
    return None


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

    # Keep only columns we know about
    known = set(RAW_COL_MAP.values())
    df = df[[c for c in df.columns if c in known]]
    return df


def filter_low_coverage(df: pd.DataFrame, min_coverage: int = 10) -> pd.DataFrame:
    """Drop events where mean per-replicate coverage (IJC+SJC) < min_coverage
    in either sample group, or where coverage data is missing for a group.

    Coverage per replicate = IJC + SJC.  For each group the average across
    replicates must be >= *min_coverage*.  Events with missing/unparseable
    count values in either group are also dropped.  If the four count columns
    are absent entirely the DataFrame is returned unchanged.
    """
    needed = {"ijc_sample_1", "sjc_sample_1", "ijc_sample_2", "sjc_sample_2"}
    if not needed.issubset(df.columns):
        return df

    def _mean_coverage(ijc_col: str, sjc_col: str) -> pd.Series:
        """Return mean per-replicate (IJC+SJC) for each row."""
        def _row_mean(ijc_val, sjc_val):
            if pd.isna(ijc_val) or pd.isna(sjc_val):
                return float("nan")
            try:
                ijc_vals = [int(x) for x in str(ijc_val).split(",") if x.strip()]
                sjc_vals = [int(x) for x in str(sjc_val).split(",") if x.strip()]
            except (ValueError, TypeError):
                return float("nan")
            if len(ijc_vals) != len(sjc_vals) or not ijc_vals:
                return float("nan")
            cov = [i + s for i, s in zip(ijc_vals, sjc_vals)]
            return sum(cov) / len(cov)

        return pd.Series(
            [_row_mean(i, s) for i, s in zip(df[ijc_col], df[sjc_col])],
            index=df.index,
        )

    mean_cov_1 = _mean_coverage("ijc_sample_1", "sjc_sample_1")
    mean_cov_2 = _mean_coverage("ijc_sample_2", "sjc_sample_2")

    # Keep rows where both groups have sufficient coverage; drop rows with missing data
    mask = (mean_cov_1 >= min_coverage) & (mean_cov_2 >= min_coverage)
    before = len(df)
    result = df[mask].reset_index(drop=True)
    dropped = before - len(result)
    if dropped:
        logger.info(
            "Coverage filter (>=%dX): dropped %d / %d events",
            min_coverage, dropped, before,
        )
    return result


def _coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce coordinate and stat columns to appropriate numeric types."""
    coord_cols = ["exon_start", "exon_end", "upstream_es", "upstream_ee",
                  "downstream_es", "downstream_ee", "second_exon_start", "second_exon_end", "rmats_id"]
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


def parse_rmats_file(content: bytes, event_type: str, analysis_id: uuid.UUID) -> pd.DataFrame:
    """
    Parse a single rMATS TSV file.

    Returns a DataFrame with normalised column names and analysis_id / event_type set.
    Rows with all-null coordinates are dropped.
    """
    df = pd.read_csv(
        io.BytesIO(content),
        sep="\t",
        na_values=["NA", "nan", ""],
        dtype=str,  # read everything as str first, coerce later
    )

    if df.empty:
        logger.warning("Empty file for event type %s", event_type)
        return pd.DataFrame()

    df = _rename_columns(df)
    df = _coerce_types(df)

    # Drop rows missing all coordinate columns
    coord_cols_present = [c for c in REQUIRED_COLS if c in df.columns]
    if coord_cols_present:
        before = len(df)
        df = df.dropna(subset=coord_cols_present, how="all")
        dropped = before - len(df)
        if dropped:
            logger.warning("Dropped %d rows with null coordinates (%s)", dropped, event_type)

    df["event_type"] = event_type
    df["analysis_id"] = str(analysis_id)

    # Computed derived column (will also be stored as a generated column in DB)
    if "inc_level_difference" in df.columns:
        df["abs_inc_level_diff"] = df["inc_level_difference"].abs()

    logger.info("Parsed %d rows for event type %s", len(df), event_type)
    return df


def deduplicate_events(df: pd.DataFrame) -> pd.DataFrame:
    """
    Deduplicate events across the whole DataFrame.
    For each unique (event_type, coordinates) key, keep the row with lowest FDR
    (NaN last), then highest |IncLevelDifference|.
    MXE events use an extended key including second exon coordinates.
    """
    if df.empty:
        return df

    # Sort so that keep='first' retains the best event
    df = df.sort_values(
        by=["fdr", "abs_inc_level_diff"],
        ascending=[True, False],
        na_position="last",
    ).reset_index(drop=True)

    parts = []
    for etype, group in df.groupby("event_type", sort=False):
        dedup_cols = DEDUP_COLS_BY_TYPE.get(str(etype), DEDUP_COLS_BY_TYPE["SE"])
        present_dedup = [c for c in dedup_cols if c in group.columns]
        deduped = group.drop_duplicates(subset=present_dedup, keep="first")
        parts.append(deduped)

    if not parts:
        return df

    result = pd.concat(parts, ignore_index=True)
    logger.info("After exact deduplication: %d rows (from %d)", len(result), len(df))
    return result


def deduplicate_with_overlap(df: pd.DataFrame, overlap_bp: int = 50) -> pd.DataFrame:
    """
    Secondary deduplication: remove events whose exon start and/or exon end are
    within *overlap_bp* bases of a more-significant event already kept.

    Within each (event_type, chr, strand) group, events are processed in order of
    increasing p_value (most significant first, NaN last).  An event is considered
    a near-duplicate of an already-kept event when:
        |exon_start_candidate − exon_start_kept| ≤ overlap_bp
        OR
        |exon_end_candidate   − exon_end_kept  | ≤ overlap_bp

    Only the most significant event (lowest p_value) of such a cluster is kept.
    """
    if df.empty:
        return df

    # Sort by p_value ASC (most significant first), NaN last, then |ΔPSI| DESC
    df = df.sort_values(
        by=["p_value", "abs_inc_level_diff"],
        ascending=[True, False],
        na_position="last",
    ).reset_index(drop=True)

    group_cols = [c for c in ["event_type", "gene_id", "chr", "strand"] if c in df.columns]
    kept_indices: list[int] = []

    for _, group_df in df.groupby(group_cols, sort=False, dropna=False):
        kept_starts: list[float] = []
        kept_ends: list[float] = []

        for idx in group_df.index:
            row = df.loc[idx]
            start_val = row.get("exon_start") if "exon_start" in df.columns else None
            end_val = row.get("exon_end") if "exon_end" in df.columns else None

            start = float(start_val) if start_val is not None and not pd.isna(start_val) else None
            end = float(end_val) if end_val is not None and not pd.isna(end_val) else None

            is_dup = False
            for ks, ke in zip(kept_starts, kept_ends):
                start_near = (start is not None and ks is not None
                              and abs(start - ks) <= overlap_bp)
                end_near = (end is not None and ke is not None
                            and abs(end - ke) <= overlap_bp)
                if start_near or end_near:
                    is_dup = True
                    break

            if not is_dup:
                kept_indices.append(int(idx))
                kept_starts.append(start)  # type: ignore[arg-type]
                kept_ends.append(end)      # type: ignore[arg-type]

    result = df.loc[kept_indices].reset_index(drop=True)
    logger.info(
        "After overlap deduplication (%d bp): %d rows (from %d)",
        overlap_bp, len(result), len(df),
    )
    return result


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
    sub = sub.where(sub.notna(), other=None)

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
    Parse all uploaded files, deduplicate, bulk-insert.

    Returns total number of events inserted.
    """
    all_dfs: list[pd.DataFrame] = []

    for filename, content in files:
        event_type = detect_event_type(filename)
        if event_type is None:
            logger.warning("Cannot infer event type from filename: %s — skipping", filename)
            continue
        parsed = parse_rmats_file(content, event_type, analysis_id)
        if not parsed.empty:
            all_dfs.append(parsed)

    if not all_dfs:
        logger.warning("No valid events parsed for analysis %s", analysis_id)
        return 0

    combined = pd.concat(all_dfs, ignore_index=True)
    combined = filter_low_coverage(combined, min_coverage=10)
    deduped = deduplicate_events(combined)
    deduped = deduplicate_with_overlap(deduped, overlap_bp=50)

    records = _df_to_records(deduped, analysis_id)

    if not records:
        return 0

    # PostgreSQL has a ~32 767 parameter limit per statement.
    # With ~25 columns per row, batches of 500 stay well within limits.
    BATCH_SIZE = 500
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i : i + BATCH_SIZE]
        stmt = (
            insert(SplicingEvent)
            .values(batch)
            .on_conflict_do_nothing(constraint="uq_splicing_event_identity")
        )
        await db.execute(stmt)
    await db.flush()

    return len(records)
