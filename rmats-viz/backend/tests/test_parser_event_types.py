"""
Type-aware parser tests (pandas only, no database).

Covers filename / header event-type detection, counting-mode detection,
A3SS / A5SS coordinate ingestion (long / short / flanking → generic columns),
type-aware deduplication and the tolerant coverage filter.

Run:  python -m pytest tests/test_parser_event_types.py -v
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pandas as pd

# Allow running from backend/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.parser import (  # noqa: E402
    deduplicate_with_overlap,
    detect_counting_mode,
    detect_event_type,
    detect_event_type_from_header,
    filter_low_coverage,
    parse_rmats_file,
)
from app.utils.composite_key import REQUIRED_COLS, REQUIRED_COLS_BY_TYPE  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

A3SS_HEADER = (
    "ID\tGeneID\tgeneSymbol\tchr\tstrand\t"
    "longExonStart_0base\tlongExonEnd\tshortES\tshortEE\tflankingES\tflankingEE\t"
    "ID.1\tIJC_SAMPLE_1\tSJC_SAMPLE_1\tIJC_SAMPLE_2\tSJC_SAMPLE_2\t"
    "IncFormLen\tSkipFormLen\t"
    "PValue\tFDR\tIncLevel1\tIncLevel2\tIncLevelDifference"
)

SE_HEADER = (
    "ID\tGeneID\tgeneSymbol\tchr\tstrand\t"
    "exonStart_0base\texonEnd\t"
    "upstreamES\tupstreamEE\tdownstreamES\tdownstreamEE\t"
    "IJC_SAMPLE_1\tSJC_SAMPLE_1\tIJC_SAMPLE_2\tSJC_SAMPLE_2\t"
    "IncFormLen\tSkipFormLen\t"
    "PValue\tFDR\tIncLevel1\tIncLevel2\tIncLevelDifference"
)

RI_HEADER = (
    "ID\tGeneID\tgeneSymbol\tchr\tstrand\t"
    "riExonStart_0base\triExonEnd\t"
    "upstreamES\tupstreamEE\tdownstreamES\tdownstreamEE\t"
    "IJC_SAMPLE_1\tSJC_SAMPLE_1\tIJC_SAMPLE_2\tSJC_SAMPLE_2\t"
    "IncFormLen\tSkipFormLen\t"
    "PValue\tFDR\tIncLevel1\tIncLevel2\tIncLevelDifference"
)

_COUNTS = "20,25\t10,12\t18,22\t8,10"
_STATS = "0.6,0.7\t0.3,0.4\t-0.3"


def _a3ss_row(
    row_id: int,
    strand: str = "+",
    long_start: int = 1000,
    long_end: int = 1100,
    short_es: int = 1003,
    short_ee: int = 1100,
    flanking_es: int = 800,
    flanking_ee: int = 900,
    fdr: float = 0.01,
    gene_id: str = "ENSG00000000001",
) -> str:
    return (
        f"{row_id}\t{gene_id}\tGENE1\tchr1\t{strand}\t"
        f"{long_start}\t{long_end}\t{short_es}\t{short_ee}\t{flanking_es}\t{flanking_ee}\t"
        f"{row_id}\t{_COUNTS}\t100\t50\t0.001\t{fdr}\t{_STATS}"
    )


def _generic_row(
    row_id: int,
    exon_start: int,
    exon_end: int,
    fdr: float = 0.01,
    gene_id: str = "ENSG00000000001",
    ijc1: str = "20,25",
    sjc1: str = "10,12",
    ijc2: str = "18,22",
    sjc2: str = "8,10",
) -> str:
    return (
        f"{row_id}\t{gene_id}\tGENE1\tchr1\t+\t"
        f"{exon_start}\t{exon_end}\t800\t900\t1200\t1300\t"
        f"{ijc1}\t{sjc1}\t{ijc2}\t{sjc2}\t100\t50\t0.001\t{fdr}\t{_STATS}"
    )


def _build(header: str, *rows: str) -> bytes:
    return (header + "\n" + "\n".join(rows) + "\n").encode()


# ---------------------------------------------------------------------------
# Event type / counting mode detection
# ---------------------------------------------------------------------------


def test_detect_event_type_from_filename():
    assert detect_event_type("SE.MATS.JC.txt") == "SE"
    assert detect_event_type("MXE.MATS.JCEC.txt") == "MXE"
    assert detect_event_type("A5SS.MATS.JC.txt") == "A5SS"
    assert detect_event_type("RI.MATS.JCEC.txt") == "RI"
    # Prefixes containing 'RI' / 'SE' as substrings must not mislead
    assert detect_event_type("PRIMARY_SE.MATS.JC.txt") == "SE"
    assert detect_event_type("MYSERIES_SE.MATS.JC.txt") == "SE"
    assert detect_event_type("results/run1/RI.MATS.JC.txt") == "RI"
    assert detect_event_type("se.mats.jc.txt") == "SE"
    # Annotation files
    assert detect_event_type("fromGTF.A3SS.txt") == "A3SS"
    assert detect_event_type("fromGTF.novelJunction.SE.txt") == "SE"
    assert detect_event_type("fromGTF.novelSpliceSite.RI.txt") == "RI"
    # Not rMATS event files
    assert detect_event_type("summary.txt") is None
    assert detect_event_type("SERIES.MATS.JC.txt") is None
    assert detect_event_type("SE.MATS.txt") is None
    assert detect_event_type("") is None


def test_detect_counting_mode():
    assert detect_counting_mode("SE.MATS.JC.txt") == "JC"
    assert detect_counting_mode("MXE.MATS.JCEC.txt") == "JCEC"
    assert detect_counting_mode("PRIMARY_SE.MATS.jcec.txt") == "JCEC"
    assert detect_counting_mode("fromGTF.A3SS.txt") is None
    assert detect_counting_mode("summary.txt") is None


def test_detect_event_type_from_header():
    assert detect_event_type_from_header(SE_HEADER.split("\t")) == "SE"
    assert detect_event_type_from_header(RI_HEADER.split("\t")) == "RI"
    mxe_cols = ["ID", "GeneID", "1stExonStart_0base", "1stExonEnd", "2ndExonStart_0base", "2ndExonEnd"]
    assert detect_event_type_from_header(mxe_cols) == "MXE"
    # A3SS and A5SS share a header: ambiguous → None
    assert detect_event_type_from_header(A3SS_HEADER.split("\t")) is None
    assert detect_event_type_from_header(["foo", "bar"]) is None


def test_required_cols_by_type():
    assert REQUIRED_COLS == set(REQUIRED_COLS_BY_TYPE["SE"])
    assert REQUIRED_COLS_BY_TYPE["RI"] == REQUIRED_COLS_BY_TYPE["SE"]
    assert {"second_exon_start", "second_exon_end"} <= REQUIRED_COLS_BY_TYPE["MXE"]
    assert REQUIRED_COLS_BY_TYPE["A3SS"] == {
        "long_exon_start", "long_exon_end", "short_es", "short_ee", "flanking_es", "flanking_ee",
    }
    assert REQUIRED_COLS_BY_TYPE["A5SS"] == REQUIRED_COLS_BY_TYPE["A3SS"]


# ---------------------------------------------------------------------------
# A3SS / A5SS parsing
# ---------------------------------------------------------------------------


def test_parse_a3ss_keeps_rows_and_fills_generic_columns():
    rows = [
        # + strand: flanking exon at lower coordinates → upstream
        _a3ss_row(0, strand="+", long_start=1000, long_end=1100, short_es=1003, short_ee=1100,
                  flanking_es=800, flanking_ee=900),
        # − strand: flanking exon at higher coordinates → downstream
        _a3ss_row(1, strand="-", long_start=2000, long_end=2100, short_es=2000, short_ee=2097,
                  flanking_es=2200, flanking_ee=2300),
    ]
    df = parse_rmats_file(_build(A3SS_HEADER, *rows), "A3SS", uuid.uuid4(), counting_mode="JC")
    assert len(df) == 2, f"A3SS rows must be kept, got {len(df)}"

    # Raw alternative-site coordinates stored
    assert df.loc[0, "long_exon_start"] == 1000
    assert df.loc[0, "long_exon_end"] == 1100
    assert df.loc[0, "short_es"] == 1003
    assert df.loc[0, "short_ee"] == 1100
    assert df.loc[0, "flanking_es"] == 800
    assert df.loc[0, "flanking_ee"] == 900

    # exon_start / exon_end mirror the long exon
    assert df.loc[0, "exon_start"] == 1000 and df.loc[0, "exon_end"] == 1100
    assert df.loc[1, "exon_start"] == 2000 and df.loc[1, "exon_end"] == 2100

    # + strand → flanking placed upstream, downstream left null
    assert df.loc[0, "upstream_es"] == 800 and df.loc[0, "upstream_ee"] == 900
    assert pd.isna(df.loc[0, "downstream_es"]) and pd.isna(df.loc[0, "downstream_ee"])

    # − strand → flanking placed downstream, upstream left null
    assert df.loc[1, "downstream_es"] == 2200 and df.loc[1, "downstream_ee"] == 2300
    assert pd.isna(df.loc[1, "upstream_es"]) and pd.isna(df.loc[1, "upstream_ee"])

    # Isoform lengths, counting mode and derived |ΔΨ| are kept
    assert df.loc[0, "inc_form_len"] == 100 and df.loc[0, "skip_form_len"] == 50
    assert (df["counting_mode"] == "JC").all()
    assert (df["event_type"] == "A3SS").all()
    assert abs(df.loc[0, "abs_inc_level_diff"] - 0.3) < 1e-9
    # pandas-renamed duplicate ID column is dropped
    assert "ID.1" not in df.columns


def test_parse_a3ss_drops_rows_with_all_null_alt_site_coords():
    null_row = (
        "5\tENSG00000000009\tGENE9\tchr1\t+\tNA\tNA\tNA\tNA\tNA\tNA\t5\t"
        f"{_COUNTS}\t100\t50\t0.001\t0.01\t{_STATS}"
    )
    df = parse_rmats_file(_build(A3SS_HEADER, _a3ss_row(0), null_row), "A3SS", uuid.uuid4())
    assert len(df) == 1
    assert df.loc[0, "rmats_id"] == 0


def test_parse_mxe_first_exon_alias():
    header = (
        "ID\tGeneID\tgeneSymbol\tchr\tstrand\t"
        "1stExonStart_0base\t1stExonEnd\t2ndExonStart_0base\t2ndExonEnd\t"
        "upstreamES\tupstreamEE\tdownstreamES\tdownstreamEE\t"
        "IJC_SAMPLE_1\tSJC_SAMPLE_1\tIJC_SAMPLE_2\tSJC_SAMPLE_2\t"
        "IncFormLen\tSkipFormLen\tPValue\tFDR\tIncLevel1\tIncLevel2\tIncLevelDifference"
    )
    row = (
        f"0\tENSG00000000001\tGENE1\tchr1\t+\t1000\t1100\t1500\t1600\t800\t900\t2000\t2100\t"
        f"{_COUNTS}\t100\t50\t0.001\t0.01\t{_STATS}"
    )
    df = parse_rmats_file(_build(header, row), "MXE", uuid.uuid4(), counting_mode="JCEC")
    assert len(df) == 1
    assert df.loc[0, "exon_start"] == 1000 and df.loc[0, "exon_end"] == 1100
    assert df.loc[0, "second_exon_start"] == 1500 and df.loc[0, "second_exon_end"] == 1600
    assert df.loc[0, "counting_mode"] == "JCEC"


# ---------------------------------------------------------------------------
# Type-aware deduplication
# ---------------------------------------------------------------------------


def test_dedup_a3ss_nagnag_sites_both_kept():
    """Two A3SS rows differing by 3 nt at shortES are distinct events."""
    rows = [
        _a3ss_row(0, short_es=1003, fdr=0.001),
        _a3ss_row(1, short_es=1006, fdr=0.05),
    ]
    df = parse_rmats_file(_build(A3SS_HEADER, *rows), "A3SS", uuid.uuid4())
    out = deduplicate_with_overlap(df, overlap_bp=50)
    assert len(out) == 2, f"NAGNAG A3SS events must both be kept, got {len(out)}"
    assert out.attrs["n_collapsed_by_type"] == {}


def test_dedup_a3ss_exact_duplicate_collapsed_lowest_fdr():
    """Identical tuple (JC vs JCEC of the same event) → one row, lowest FDR."""
    rows = [
        _a3ss_row(0, fdr=0.05),
        _a3ss_row(1, fdr=0.001),
    ]
    df = parse_rmats_file(_build(A3SS_HEADER, *rows), "A3SS", uuid.uuid4())
    out = deduplicate_with_overlap(df, overlap_bp=50)
    assert len(out) == 1
    assert out.loc[0, "fdr"] == 0.001
    assert out.attrs["n_collapsed_by_type"] == {"A3SS": 1}


def test_dedup_se_rows_30nt_apart_collapse():
    rows = [
        _generic_row(0, 1000, 1100, fdr=0.001),
        _generic_row(1, 1030, 1130, fdr=0.05),   # both boundaries 30 nt away
        _generic_row(2, 5000, 5200, fdr=0.01),
    ]
    df = parse_rmats_file(_build(SE_HEADER, *rows), "SE", uuid.uuid4())
    out = deduplicate_with_overlap(df, overlap_bp=50)
    assert sorted(out["exon_start"].tolist()) == [1000, 5000]
    assert out.attrs["n_collapsed_by_type"] == {"SE": 1}


def test_dedup_se_single_shared_boundary_collapses():
    """SE uses the OR rule: sharing only the end boundary is enough."""
    rows = [
        _generic_row(0, 1000, 1100, fdr=0.001),
        _generic_row(1, 1300, 1120, fdr=0.05),
    ]
    df = parse_rmats_file(_build(SE_HEADER, *rows), "SE", uuid.uuid4())
    out = deduplicate_with_overlap(df, overlap_bp=50)
    assert len(out) == 1 and out.loc[0, "exon_start"] == 1000


def test_dedup_ri_single_shared_boundary_not_collapsed():
    """RI uses the AND rule: rows sharing only one boundary are distinct."""
    rows = [
        _generic_row(0, 1000, 1100, fdr=0.001),
        _generic_row(1, 1000, 1400, fdr=0.05),   # same start, end 300 nt away
    ]
    df = parse_rmats_file(_build(RI_HEADER, *rows), "RI", uuid.uuid4())
    assert len(df) == 2
    out = deduplicate_with_overlap(df, overlap_bp=50)
    assert len(out) == 2, f"RI rows sharing one boundary must be kept, got {len(out)}"
    assert out.attrs["n_collapsed_by_type"] == {}


def test_dedup_ri_both_boundaries_close_collapsed():
    rows = [
        _generic_row(0, 1000, 1100, fdr=0.001),
        _generic_row(1, 1010, 1090, fdr=0.05),
    ]
    df = parse_rmats_file(_build(RI_HEADER, *rows), "RI", uuid.uuid4())
    out = deduplicate_with_overlap(df, overlap_bp=50)
    assert len(out) == 1 and out.loc[0, "fdr"] == 0.001
    assert out.attrs["n_collapsed_by_type"] == {"RI": 1}


def test_dedup_se_order_independent_of_input_position():
    """Lowest-FDR row wins regardless of file order; bisect path handles
    kept events inserted out of coordinate order."""
    rows = [
        _generic_row(0, 3000, 3100, fdr=0.02),
        _generic_row(1, 1000, 1100, fdr=0.001),
        _generic_row(2, 2000, 2100, fdr=0.01),
        _generic_row(3, 2040, 2500, fdr=0.03),   # start within 50 of 2000 → dup
        _generic_row(4, 3500, 3120, fdr=0.04),   # end within 50 of 3100 → dup
        _generic_row(5, 1060, 1200, fdr=0.05),   # start 60 from 1000, end 100 from 1100 → kept
    ]
    df = parse_rmats_file(_build(SE_HEADER, *rows), "SE", uuid.uuid4())
    out = deduplicate_with_overlap(df, overlap_bp=50)
    assert sorted(out["exon_start"].tolist()) == [1000, 1060, 2000, 3000]
    assert out.attrs["n_collapsed_by_type"] == {"SE": 2}


def test_dedup_empty_frame():
    out = deduplicate_with_overlap(pd.DataFrame(), overlap_bp=50)
    assert out.empty
    assert out.attrs["n_collapsed_by_type"] == {}


# ---------------------------------------------------------------------------
# Coverage filter over available replicates
# ---------------------------------------------------------------------------


def test_coverage_one_na_replicate_kept_when_others_sufficient():
    """Group 1: replicates (20+10, NA, 15+5) → mean over available = 25 ≥ 10 → kept."""
    row = _generic_row(0, 1000, 1100, ijc1="20,NA,15", sjc1="10,12,5", ijc2="18,22", sjc2="8,10")
    df = parse_rmats_file(_build(SE_HEADER, row), "SE", uuid.uuid4())
    out = filter_low_coverage(df, min_coverage=10)
    assert len(out) == 1
    assert out.attrs["n_dropped_low_coverage"] == 0
    assert out.attrs["n_dropped_missing_counts"] == 0


def test_coverage_one_na_replicate_dropped_when_others_low():
    row = _generic_row(0, 1000, 1100, ijc1="2,NA,3", sjc1="1,12,1", ijc2="18,22", sjc2="8,10")
    df = parse_rmats_file(_build(SE_HEADER, row), "SE", uuid.uuid4())
    out = filter_low_coverage(df, min_coverage=10)
    assert len(out) == 0
    assert out.attrs["n_dropped_low_coverage"] == 1
    assert out.attrs["n_dropped_missing_counts"] == 0


def test_coverage_group_without_parseable_replicate_dropped():
    row = _generic_row(0, 1000, 1100, ijc1="NA,NA", sjc1="10,12", ijc2="18,22", sjc2="8,10")
    df = parse_rmats_file(_build(SE_HEADER, row), "SE", uuid.uuid4())
    out = filter_low_coverage(df, min_coverage=10)
    assert len(out) == 0
    assert out.attrs["n_dropped_missing_counts"] == 1
    assert out.attrs["n_dropped_low_coverage"] == 0


def test_coverage_unequal_replicate_lists_use_paired_replicates():
    """IJC has 3 replicates, SJC has 2 → the first two pairs are used."""
    row = _generic_row(0, 1000, 1100, ijc1="20,25,1", sjc1="10,12", ijc2="18,22", sjc2="8,10")
    df = parse_rmats_file(_build(SE_HEADER, row), "SE", uuid.uuid4())
    out = filter_low_coverage(df, min_coverage=10)
    assert len(out) == 1


def test_coverage_missing_count_columns_returns_unchanged():
    """Annotation-only input (fromGTF) has no count columns → no filtering."""
    df = pd.DataFrame({"event_type": ["SE"], "exon_start": [1000], "exon_end": [1100]})
    out = filter_low_coverage(df, min_coverage=10)
    assert len(out) == 1
    assert out.attrs["n_dropped_low_coverage"] == 0
    assert out.attrs["n_dropped_missing_counts"] == 0
