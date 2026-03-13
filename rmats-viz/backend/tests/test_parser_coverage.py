"""
Test parser functions with simulated rMATS SE files.

Focuses on the coverage filter (>=10X per group) and the full
parse → filter → deduplicate pipeline.

Run:  python -m pytest tests/test_parser_coverage.py -v
  or: python tests/test_parser_coverage.py
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pandas as pd

# Allow running from backend/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.parser import (
    detect_event_type,
    filter_low_coverage,
    parse_rmats_file,
    deduplicate_events,
    deduplicate_with_overlap,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SE_HEADER = (
    "ID\tGeneID\tgeneSymbol\tchr\tstrand\t"
    "exonStart_0base\texonEnd\t"
    "upstreamES\tupstreamEE\tdownstreamES\tdownstreamEE\t"
    "IJC_SAMPLE_1\tSJC_SAMPLE_1\tIJC_SAMPLE_2\tSJC_SAMPLE_2\t"
    "IncFormLen\tSkipFormLen\t"
    "PValue\tFDR\tIncLevel1\tIncLevel2\tIncLevelDifference"
)


def _make_se_row(
    row_id: int,
    gene_id: str = "ENSG00000100001",
    gene_symbol: str = "GENE1",
    chrom: str = "chr1",
    strand: str = "+",
    exon_start: int = 1000,
    exon_end: int = 1100,
    upstream_es: int = 800,
    upstream_ee: int = 900,
    downstream_es: int = 1200,
    downstream_ee: int = 1300,
    ijc1: str = "20,25",
    sjc1: str = "10,12",
    ijc2: str = "18,22",
    sjc2: str = "8,10",
    pvalue: float = 0.001,
    fdr: float = 0.01,
    inc1: str = "0.6,0.7",
    inc2: str = "0.3,0.4",
    inc_diff: float = -0.3,
) -> str:
    return (
        f"{row_id}\t{gene_id}\t{gene_symbol}\t{chrom}\t{strand}\t"
        f"{exon_start}\t{exon_end}\t"
        f"{upstream_es}\t{upstream_ee}\t{downstream_es}\t{downstream_ee}\t"
        f"{ijc1}\t{sjc1}\t{ijc2}\t{sjc2}\t"
        f"100\t50\t"
        f"{pvalue}\t{fdr}\t{inc1}\t{inc2}\t{inc_diff}"
    )


def _build_se_file(*rows: str) -> bytes:
    return (SE_HEADER + "\n" + "\n".join(rows) + "\n").encode()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_detect_event_type():
    assert detect_event_type("SE.MATS.JC.txt") == "SE"
    assert detect_event_type("RI.MATS.JCEC.txt") == "RI"
    assert detect_event_type("A3SS.MATS.JC.txt") == "A3SS"
    assert detect_event_type("MXE.MATS.JC.txt") == "MXE"
    assert detect_event_type("random.txt") is None
    print("  PASS  detect_event_type")


def test_filter_keeps_high_coverage():
    """Events with >=10X coverage in both groups should be kept."""
    row = _make_se_row(0, ijc1="20,30", sjc1="10,15", ijc2="25,20", sjc2="10,10")
    content = _build_se_file(row)
    df = parse_rmats_file(content, "SE", uuid.uuid4())
    filtered = filter_low_coverage(df, min_coverage=10)
    assert len(filtered) == 1, f"Expected 1 row, got {len(filtered)}"
    print("  PASS  filter keeps high coverage events")


def test_filter_drops_low_coverage_group1():
    """Events with <10X mean coverage in group 1 should be dropped."""
    # Group 1: IJC=1,2 + SJC=1,1 → per-replicate coverage = 2,3 → mean=2.5 < 10
    row = _make_se_row(0, ijc1="1,2", sjc1="1,1", ijc2="20,25", sjc2="10,10")
    content = _build_se_file(row)
    df = parse_rmats_file(content, "SE", uuid.uuid4())
    filtered = filter_low_coverage(df, min_coverage=10)
    assert len(filtered) == 0, f"Expected 0 rows, got {len(filtered)}"
    print("  PASS  filter drops low coverage in group 1")


def test_filter_drops_low_coverage_group2():
    """Events with <10X mean coverage in group 2 should be dropped."""
    # Group 2: IJC=2,3 + SJC=1,1 → per-replicate coverage = 3,4 → mean=3.5 < 10
    row = _make_se_row(0, ijc1="20,25", sjc1="10,10", ijc2="2,3", sjc2="1,1")
    content = _build_se_file(row)
    df = parse_rmats_file(content, "SE", uuid.uuid4())
    filtered = filter_low_coverage(df, min_coverage=10)
    assert len(filtered) == 0, f"Expected 0 rows, got {len(filtered)}"
    print("  PASS  filter drops low coverage in group 2")


def test_filter_boundary_exactly_10():
    """Events with exactly 10X mean coverage should be kept."""
    # Per-replicate: IJC+SJC = 5+5=10, 6+4=10 → mean=10 → kept
    row = _make_se_row(0, ijc1="5,6", sjc1="5,4", ijc2="7,8", sjc2="3,2")
    content = _build_se_file(row)
    df = parse_rmats_file(content, "SE", uuid.uuid4())
    filtered = filter_low_coverage(df, min_coverage=10)
    assert len(filtered) == 1, f"Expected 1 row (boundary), got {len(filtered)}"
    print("  PASS  filter keeps boundary exactly 10X")


def test_filter_boundary_just_below_10():
    """Events with mean coverage just below 10 should be dropped."""
    # Per-replicate: IJC+SJC = 5+4=9, 5+4=9 → mean=9 < 10
    row = _make_se_row(0, ijc1="5,5", sjc1="4,4", ijc2="20,20", sjc2="10,10")
    content = _build_se_file(row)
    df = parse_rmats_file(content, "SE", uuid.uuid4())
    filtered = filter_low_coverage(df, min_coverage=10)
    assert len(filtered) == 0, f"Expected 0 rows (below 10X), got {len(filtered)}"
    print("  PASS  filter drops events just below 10X")


def test_filter_single_replicate():
    """Works correctly with a single replicate (no commas)."""
    row = _make_se_row(0, ijc1="15", sjc1="5", ijc2="12", sjc2="8")
    content = _build_se_file(row)
    df = parse_rmats_file(content, "SE", uuid.uuid4())
    filtered = filter_low_coverage(df, min_coverage=10)
    # Group 1: 15+5=20 >= 10, Group 2: 12+8=20 >= 10
    assert len(filtered) == 1, f"Expected 1 row, got {len(filtered)}"
    print("  PASS  filter works with single replicate")


def test_filter_mixed_events():
    """Mix of high and low coverage events — only high coverage kept."""
    rows = [
        # High coverage (keep)
        _make_se_row(0, exon_start=1000, ijc1="30,40", sjc1="10,10", ijc2="25,30", sjc2="10,10"),
        # Low coverage group 1 (drop)
        _make_se_row(1, exon_start=2000, ijc1="1,1", sjc1="1,1", ijc2="30,30", sjc2="10,10"),
        # High coverage (keep)
        _make_se_row(2, exon_start=3000, ijc1="50,60", sjc1="20,20", ijc2="40,40", sjc2="15,15"),
        # Low coverage group 2 (drop)
        _make_se_row(3, exon_start=4000, ijc1="30,30", sjc1="10,10", ijc2="2,2", sjc2="1,1"),
    ]
    content = _build_se_file(*rows)
    df = parse_rmats_file(content, "SE", uuid.uuid4())
    assert len(df) == 4, f"Parsed {len(df)} rows, expected 4"
    filtered = filter_low_coverage(df, min_coverage=10)
    assert len(filtered) == 2, f"Expected 2 rows after filter, got {len(filtered)}"
    # Verify correct rows kept (exon_start 1000 and 3000)
    kept_starts = sorted(filtered["exon_start"].tolist())
    assert kept_starts == [1000, 3000], f"Wrong rows kept: {kept_starts}"
    print("  PASS  filter mixed events correctly")


def test_full_pipeline_parse_filter_dedup():
    """End-to-end: parse → coverage filter → dedup removes low-cov and duplicates."""
    aid = uuid.uuid4()
    rows = [
        # Event A: high coverage, best FDR
        _make_se_row(0, gene_id="ENSG00000000001", exon_start=1000, exon_end=1100,
                     ijc1="30,40", sjc1="10,15", ijc2="25,30", sjc2="10,12",
                     fdr=0.001, pvalue=0.0001),
        # Event A duplicate: same coordinates, worse FDR → dedup should remove
        _make_se_row(1, gene_id="ENSG00000000001", exon_start=1000, exon_end=1100,
                     ijc1="20,20", sjc1="10,10", ijc2="15,20", sjc2="10,10",
                     fdr=0.05, pvalue=0.01),
        # Event B: low coverage → filter should remove
        _make_se_row(2, gene_id="ENSG00000000002", exon_start=5000, exon_end=5200,
                     ijc1="1,2", sjc1="0,1", ijc2="1,1", sjc2="0,0",
                     fdr=0.001, pvalue=0.0001),
        # Event C: high coverage, unique coordinates → keep
        _make_se_row(3, gene_id="ENSG00000000003", exon_start=9000, exon_end=9300,
                     ijc1="50,60", sjc1="20,25", ijc2="40,50", sjc2="15,20",
                     fdr=0.01, pvalue=0.001),
    ]
    content = _build_se_file(*rows)
    df = parse_rmats_file(content, "SE", aid)
    assert len(df) == 4

    # Coverage filter
    df = filter_low_coverage(df, min_coverage=10)
    assert len(df) == 3, f"After coverage filter: expected 3, got {len(df)}"

    # Exact dedup
    df = deduplicate_events(df)
    assert len(df) == 2, f"After dedup: expected 2, got {len(df)}"

    # Verify the kept events
    kept_starts = sorted(df["exon_start"].tolist())
    assert kept_starts == [1000, 9000], f"Wrong events kept: {kept_starts}"

    # The event at 1000 should have the better FDR
    event_a = df[df["exon_start"] == 1000].iloc[0]
    assert event_a["fdr"] == 0.001, f"Wrong FDR kept: {event_a['fdr']}"

    print("  PASS  full pipeline (parse → filter → dedup)")


def test_overlap_dedup_after_coverage_filter():
    """Overlap dedup removes near-duplicate exons within 50bp."""
    aid = uuid.uuid4()
    rows = [
        # Event at 1000-1100, most significant
        _make_se_row(0, exon_start=1000, exon_end=1100,
                     ijc1="30,30", sjc1="10,10", ijc2="25,25", sjc2="10,10",
                     pvalue=0.0001, fdr=0.001),
        # Event at 1030-1100, within 50bp of the first → overlap dedup should remove
        _make_se_row(1, exon_start=1030, exon_end=1100,
                     ijc1="20,20", sjc1="10,10", ijc2="20,20", sjc2="10,10",
                     pvalue=0.01, fdr=0.05),
        # Event at 5000-5200, far away → keep
        _make_se_row(2, exon_start=5000, exon_end=5200,
                     ijc1="40,40", sjc1="15,15", ijc2="30,30", sjc2="12,12",
                     pvalue=0.001, fdr=0.01),
    ]
    content = _build_se_file(*rows)
    df = parse_rmats_file(content, "SE", aid)
    df = filter_low_coverage(df, min_coverage=10)
    assert len(df) == 3

    df = deduplicate_events(df)
    df = deduplicate_with_overlap(df, overlap_bp=50)
    assert len(df) == 2, f"After overlap dedup: expected 2, got {len(df)}"

    kept_starts = sorted(df["exon_start"].tolist())
    assert kept_starts == [1000, 5000], f"Wrong events after overlap dedup: {kept_starts}"
    print("  PASS  overlap dedup after coverage filter")


def test_three_replicates():
    """Correctly averages across 3 replicates."""
    # Group 1: (5+2, 4+3, 6+1) = (7, 7, 7) → mean=7 < 10 → drop
    row = _make_se_row(0, ijc1="5,4,6", sjc1="2,3,1", ijc2="20,20,20", sjc2="10,10,10")
    content = _build_se_file(row)
    df = parse_rmats_file(content, "SE", uuid.uuid4())
    filtered = filter_low_coverage(df, min_coverage=10)
    assert len(filtered) == 0, f"Expected 0 (mean=7 < 10), got {len(filtered)}"

    # Group 1: (8+5, 7+6, 9+4) = (13, 13, 13) → mean=13 >= 10 → keep
    row2 = _make_se_row(0, ijc1="8,7,9", sjc1="5,6,4", ijc2="20,20,20", sjc2="10,10,10")
    content2 = _build_se_file(row2)
    df2 = parse_rmats_file(content2, "SE", uuid.uuid4())
    filtered2 = filter_low_coverage(df2, min_coverage=10)
    assert len(filtered2) == 1, f"Expected 1 (mean=13 >= 10), got {len(filtered2)}"
    print("  PASS  three replicates averaging")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

ALL_TESTS = [
    test_detect_event_type,
    test_filter_keeps_high_coverage,
    test_filter_drops_low_coverage_group1,
    test_filter_drops_low_coverage_group2,
    test_filter_boundary_exactly_10,
    test_filter_boundary_just_below_10,
    test_filter_single_replicate,
    test_filter_mixed_events,
    test_full_pipeline_parse_filter_dedup,
    test_overlap_dedup_after_coverage_filter,
    test_three_replicates,
]

if __name__ == "__main__":
    passed = 0
    failed = 0
    for test_fn in ALL_TESTS:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  FAIL  {test_fn.__name__}: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    if failed:
        sys.exit(1)
    print("All tests passed!")
