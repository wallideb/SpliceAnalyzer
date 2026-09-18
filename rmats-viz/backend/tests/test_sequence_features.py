"""
Tests for the sequence / splice-feature / MANE services.

No database, no samtools, no network: samtools is simulated by
monkeypatching ``subprocess.run`` and the MANE GFF3 is a small gzip file
written to a temporary directory.

Run:  python -m pytest tests/test_sequence_features.py -q
"""
from __future__ import annotations

import gzip
import subprocess
import sys
from pathlib import Path

import pytest

# Allow running from backend/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import mane as mane_mod
from app.services import mane_local
from app.services import sequence as seq_mod
from app.services.sequence import (
    SpliceWindows,
    _parse_faidx_output,
    extract_regions_batch,
    reverse_complement,
    splice_window_coords,
)
from app.services.splice_features import (
    _BP_MAX_DISTANCE,
    _BP_MIN_DISTANCE,
    compute_features,
    compute_pwm,
    find_branch_point,
)


# ---------------------------------------------------------------------------
# reverse_complement — full IUPAC
# ---------------------------------------------------------------------------

def test_reverse_complement_basic():
    assert reverse_complement("ACGT") == "ACGT"
    assert reverse_complement("AAGGTCC") == "GGACCTT"
    assert reverse_complement("") == ""


def test_reverse_complement_iupac_upper():
    assert reverse_complement("ACGTRYSWKMBDHVN") == "NBDHVKMWSRYACGT"
    # Pairs: R<->Y, K<->M, B<->V, D<->H; S, W, N self-complementary
    for a, b in (("R", "Y"), ("K", "M"), ("B", "V"), ("D", "H")):
        assert reverse_complement(a) == b
        assert reverse_complement(b) == a
    for x in "SWN":
        assert reverse_complement(x) == x


def test_reverse_complement_lowercase_and_uracil():
    assert reverse_complement("acgtryswkmbdhvn") == "nbdhvkmwsryacgt"
    assert reverse_complement("AcGt") == "aCgT"
    # U is treated as T -> complement A
    assert reverse_complement("U") == "A"
    assert reverse_complement("AUG") == "CAT"
    assert reverse_complement("u") == "a"


def test_reverse_complement_is_involution_on_iupac():
    s = "ACGTRYSWKMBDHVNacgtryswkmbdhvn"
    assert reverse_complement(reverse_complement(s)) == s


# ---------------------------------------------------------------------------
# splice_window_coords — literal intervals
# ---------------------------------------------------------------------------

def test_splice_window_coords_plus_strand():
    se_start, se_end = 1000, 1100
    up_es, up_ee, dn_es, dn_ee = 500, 600, 1500, 1600
    w = splice_window_coords("+", se_start, se_end, up_es, up_ee, dn_es, dn_ee)
    assert set(w) == {"donor", "acceptor", "ppt", "upstream_donor", "downstream_acceptor"}
    assert w["donor"] == (se_end - 3, se_end + 6) == (1097, 1106)
    assert w["acceptor"] == (se_start - 20, se_start + 3) == (980, 1003)
    assert w["ppt"] == (se_start - 50, se_start - 3) == (950, 997)
    assert w["upstream_donor"] == (up_ee - 3, up_ee + 6) == (597, 606)
    assert w["downstream_acceptor"] == (dn_es - 20, dn_es + 3) == (1480, 1503)
    # window sizes
    assert w["donor"][1] - w["donor"][0] == 9
    assert w["acceptor"][1] - w["acceptor"][0] == 23
    assert w["ppt"][1] - w["ppt"][0] == 47


def test_splice_window_coords_minus_strand():
    se_start, se_end = 1000, 1100
    up_es, up_ee, dn_es, dn_ee = 500, 600, 1500, 1600
    w = splice_window_coords("-", se_start, se_end, up_es, up_ee, dn_es, dn_ee)
    assert w["donor"] == (se_start - 6, se_start + 3) == (994, 1003)
    assert w["acceptor"] == (se_end - 3, se_end + 20) == (1097, 1120)
    assert w["ppt"] == (se_end + 3, se_end + 50) == (1103, 1150)
    # rMATS "downstream" exon (higher coords) is the 5' flanking exon on '-'
    assert w["upstream_donor"] == (dn_es - 6, dn_es + 3) == (1494, 1503)
    # rMATS "upstream" exon (lower coords) is the 3' flanking exon on '-'
    assert w["downstream_acceptor"] == (up_ee - 3, up_ee + 20) == (597, 620)


def test_splice_window_coords_missing_flanks():
    w = splice_window_coords("+", 1000, 1100, None, None, None, None)
    assert w["upstream_donor"] is None
    assert w["downstream_acceptor"] is None
    assert w["donor"] == (1097, 1106)
    w = splice_window_coords("-", 1000, 1100, None, None, None, None)
    assert w["upstream_donor"] is None
    assert w["downstream_acceptor"] is None
    # '-' strand: upstream_donor depends on downstream_es only
    w = splice_window_coords("-", 1000, 1100, None, None, 1500, None)
    assert w["upstream_donor"] == (1494, 1503)
    assert w["downstream_acceptor"] is None


# ---------------------------------------------------------------------------
# Branch point
# ---------------------------------------------------------------------------

def _ppt_with_motif_at(distance: int, motif: str = "TACTAAC") -> str:
    """Build a 47-nt PPT window (ends 3 nt before the exon) whose 7-mer
    *motif* has its branch A (index 5) at *distance* nt from the exon start."""
    n = 47
    # distance = (n + 3) - (i + 5)  ->  i = n + 3 - 5 - distance
    i = n + 3 - 5 - distance
    assert 0 <= i <= n - 7
    seq = "T" * i + motif + "T" * (n - i - 7)
    assert len(seq) == n
    return seq


def test_find_branch_point_perfect_motif_at_minus_25():
    seq = _ppt_with_motif_at(25)
    assert seq[20:27] == "TACTAAC"
    pos, score, dist = find_branch_point(seq, offset_to_exon=3)
    assert pos == 20
    assert score == 7
    assert dist == 25


def test_find_branch_point_too_close_not_found():
    seq = _ppt_with_motif_at(10)
    assert "TACTAAC" in seq
    pos, score, dist = find_branch_point(seq, offset_to_exon=3)
    assert (pos, score, dist) == (-1, 0, -1)


def test_find_branch_point_requires_adenosine():
    # YNYTRAY with G instead of the branch A (all other positions match)
    seq = "T" * 20 + "TCCTGGC" + "T" * 20
    assert len(seq) == 47
    pos, score, dist = find_branch_point(seq, offset_to_exon=3)
    assert (pos, score, dist) == (-1, 0, -1)


def test_find_branch_point_ties_prefer_closest_to_3ss():
    # Two perfect motifs, branch A at -35 and -25: the most 3' one wins.
    n = 47
    i_far = n + 3 - 5 - 35   # 10
    i_near = n + 3 - 5 - 25  # 20
    seq = list("T" * n)
    seq[i_far:i_far + 7] = "TACTAAC"
    seq[i_near:i_near + 7] = "TACTAAC"
    seq = "".join(seq)
    pos, score, dist = find_branch_point(seq, offset_to_exon=3)
    assert score == 7
    assert pos == i_near
    assert dist == 25


def test_find_branch_point_distance_window_constants():
    assert (_BP_MIN_DISTANCE, _BP_MAX_DISTANCE) == (18, 44)
    # Use a perfect YNYTRAY whose only A is the branch A, so that no
    # secondary candidate exists inside the window.
    motif = "TCCTGAC"
    # A at exactly -18 and -44 are accepted; -17 and -45 are not.
    for d in (18, 44):
        pos, score, dist = find_branch_point(_ppt_with_motif_at(d, motif), 3)
        assert dist == d and score == 7
    for d in (17, 45):
        assert find_branch_point(_ppt_with_motif_at(d, motif), 3) == (-1, 0, -1)


def test_compute_features_branch_point_fields():
    ppt = _ppt_with_motif_at(25)
    windows = SpliceWindows(
        donor_seq="CAGGTAAGT",
        acceptor_seq="T" * 18 + "AG" + "GCA",
        ppt_seq=ppt,
    )
    ev = {"exon_start": 1000, "exon_end": 1100, "strand": "+",
          "upstream_es": 500, "upstream_ee": 600,
          "downstream_es": 1500, "downstream_ee": 1600}
    res = compute_features(ev, windows)
    assert res.bp_motif_found is True
    assert res.bp_distance == 25          # branch A -> exon start
    assert res.bp_score == 7
    assert res.bp_position == 20
    assert res.bp_motif == "TACTAAC"
    assert res.donor_is_gt is True
    assert res.acceptor_is_ag is True


def test_compute_features_branch_point_not_found_fields():
    windows = SpliceWindows(donor_seq="", acceptor_seq="", ppt_seq="T" * 47)
    res = compute_features({"exon_start": 0, "exon_end": 10}, windows)
    assert res.bp_motif_found is False
    assert res.bp_distance is None
    assert res.bp_position is None
    assert res.bp_motif is None
    assert res.bp_score == 0


# ---------------------------------------------------------------------------
# PWM / GT-AG
# ---------------------------------------------------------------------------

def test_compute_pwm_ignores_n_in_denominator():
    pwm = compute_pwm(["A", "A", "N", "C"])
    assert pwm[0]["A"] == 0.6667
    assert pwm[0]["C"] == 0.3333
    assert pwm[0]["G"] == 0.0
    assert abs(sum(pwm[0].values()) - 1.0) < 1e-3
    # column of only N -> fallback denominator 1, all zeros
    assert compute_pwm(["N", "N"])[0] == {"A": 0.0, "C": 0.0, "G": 0.0, "T": 0.0}
    assert compute_pwm([]) == []


def test_acceptor_is_ag_none_for_short_window():
    windows = SpliceWindows(
        donor_seq="CAGG",                        # < 5 nt
        acceptor_seq="TTTTTTTTTTTTTTTTTAG",      # 19 nt (< 20)
        ppt_seq="",
        upstream_donor_seq="",
        downstream_acceptor_seq="T" * 18 + "AGG",  # 21 nt (>= 20)
    )
    res = compute_features({"exon_start": 0, "exon_end": 10}, windows)
    assert res.acceptor_is_ag is None
    assert res.donor_is_gt is None
    assert res.upstream_donor_is_gt is None
    assert res.downstream_acceptor_is_ag is True
    # exactly 20 nt with AG at 18-19 is evaluable
    windows.acceptor_seq = "T" * 18 + "AG"
    windows.donor_seq = "CAGGT"
    res = compute_features({"exon_start": 0, "exon_end": 10}, windows)
    assert res.acceptor_is_ag is True
    assert res.donor_is_gt is True
    windows.acceptor_seq = "T" * 18 + "AC"
    res = compute_features({"exon_start": 0, "exon_end": 10}, windows)
    assert res.acceptor_is_ag is False


# ---------------------------------------------------------------------------
# FASTA (samtools faidx) output parsing
# ---------------------------------------------------------------------------

def test_parse_faidx_output_empty_record_does_not_shift():
    text = ">chr1:1-4\nACGT\n>chr1:0-0\n>chr1:5-8\nGGCC\n"
    assert _parse_faidx_output(text, 3) == ["ACGT", "", "GGCC"]


def test_parse_faidx_output_multiline_and_case():
    text = ">a\nac\ngt\n>b\nGG\n"
    assert _parse_faidx_output(text, 2) == ["ACGT", "GG"]


def test_parse_faidx_output_count_mismatch_blanks_chunk():
    text = ">a\nACGT\n>b\nGG\n"
    assert _parse_faidx_output(text, 3) == ["", "", ""]
    assert _parse_faidx_output("", 2) == ["", ""]


def _fake_samtools(bad_regions: set[str], calls: list[list[str]]):
    """Return a subprocess.run replacement that fails whenever any region of
    the call is in *bad_regions*, and otherwise returns the region name as the
    sequence (so assignment can be verified)."""

    def run(args, **kwargs):
        calls.append(list(args))
        regions = args[3:]
        if any(r in bad_regions for r in regions):
            raise subprocess.CalledProcessError(1, args, stderr="[faidx] failed")
        out = "".join(f">{r}\n{r.replace(':', '_')}\n" for r in regions)
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")

    return run


def test_extract_regions_batch_retries_only_invalid_regions(monkeypatch):
    calls: list[list[str]] = []
    bad = {"chr1:31-40"}
    monkeypatch.setattr(seq_mod.subprocess, "run", _fake_samtools(bad, calls))
    monkeypatch.setattr(seq_mod, "_fai_contig_set", lambda fp: set())  # pass-through contigs
    regions = [("chr1", 0, 10), ("chr1", 10, 20), ("chr1", 20, 30),
               ("chr1", 30, 40), ("chr1", 40, 50)]
    out = extract_regions_batch(regions, "/nonexistent.fa")
    assert out == ["CHR1_1-10", "CHR1_11-20", "CHR1_21-30", "", "CHR1_41-50"]
    # first call was the whole chunk, then halves down to single regions
    assert len(calls[0]) == 3 + 5
    assert len(calls) > 1


def test_extract_regions_batch_clamps_negative_start_and_skips_invalid(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(seq_mod.subprocess, "run", _fake_samtools(set(), calls))
    monkeypatch.setattr(seq_mod, "_fai_contig_set", lambda fp: set())
    regions = [("chr1", -5, 10), ("chr1", -5, -2), ("chr1", 20, 20), ("chr1", 20, 25)]
    out = extract_regions_batch(regions, "/nonexistent.fa")
    assert out == ["CHR1_1-10", "", "", "CHR1_21-25"]
    # only the two valid regions were passed to samtools
    assert calls[0][3:] == ["chr1:1-10", "chr1:21-25"]
    assert extract_regions_batch([], "/nonexistent.fa") == []


def test_get_splice_windows_batch_uses_window_coords(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(seq_mod.subprocess, "run", _fake_samtools(set(), calls))
    monkeypatch.setattr(seq_mod, "_fai_contig_set", lambda fp: set())
    events = [("chr1", "+", 1000, 1100, 500, 600, 1500, 1600),
              ("chr2", "-", 1000, 1100, None, None, None, None)]
    res = seq_mod.get_splice_windows_batch(events, "/nonexistent.fa")
    assert len(res) == 2
    assert res[0].donor_seq == "CHR1_1098-1106"
    assert res[0].acceptor_seq == "CHR1_981-1003"
    assert res[0].ppt_seq == "CHR1_951-997"
    assert res[0].upstream_donor_seq == "CHR1_598-606"
    assert res[0].downstream_acceptor_seq == "CHR1_1481-1503"
    # '-' strand: sequences are reverse-complemented; missing flanks are ""
    assert res[1].donor_seq == reverse_complement("CHR2_995-1003")
    assert res[1].upstream_donor_seq == ""
    assert res[1].downstream_acceptor_seq == ""


# ---------------------------------------------------------------------------
# MANE (Ensembl REST path) — CDS filtering and union-based frame class
# ---------------------------------------------------------------------------

def test_filter_cds_by_transcript_accepts_versioned_parent():
    cds = [
        {"Parent": "ENST00000000001", "start": 1, "end": 10},
        {"Parent": "ENST00000000001.7", "start": 11, "end": 20},
        {"Parent": "ENST00000000002", "start": 21, "end": 30},
        {"Parent": "ENST000000000010", "start": 31, "end": 40},
        {"start": 41, "end": 50},
    ]
    kept = mane_mod._filter_cds_by_transcript(cds, "ENST00000000001")
    assert [c["start"] for c in kept] == [1, 11]
    kept = mane_mod._filter_cds_by_transcript(cds, "ENST00000000001.3")
    assert [c["start"] for c in kept] == [1, 11]
    assert mane_mod._filter_cds_by_transcript(None, "ENST00000000001") == []


def test_frame_class_uses_union_of_cds_segments():
    # Ensembl 1-based inclusive: CDS segments [100,199] and [300,399]
    tx = {
        "strand": 1,
        "Exon": [{"start": 100, "end": 199}, {"start": 300, "end": 399}],
        "CDS": [{"start": 100, "end": 199}, {"start": 300, "end": 399}],
    }
    # exon fully inside one CDS segment (0-based [120, 180) = 60 nt)
    r = mane_mod._frame_class(120, 180, tx)
    assert r["frame_region"] == "CDS"
    assert r["cds_exon_length"] == 60
    assert r["frame_class"] == "in_frame"
    # exon in the gap between segments: inside the span but no CDS coverage
    r = mane_mod._frame_class(210, 280, tx)
    assert r["frame_class"] == "non_coding"
    # exon spanning the gap: overlap is the sum over segments, region partial
    r = mane_mod._frame_class(150, 350, tx)
    assert r["cds_exon_length"] == (199 - 150) + (350 - 299)
    assert r["frame_region"] == "partial"
    # exon extending beyond the union span
    r = mane_mod._frame_class(50, 150, tx)
    assert r["frame_region"] == "partial"
    assert r["cds_exon_length"] == 150 - 99
    # exon entirely upstream of CDS on + strand → UTR5
    r = mane_mod._frame_class(10, 50, tx)
    assert r["frame_region"] == "UTR5" and r["frame_class"] == "non_coding"


def test_ensembl_chrom_normalisation():
    assert mane_mod._ensembl_chrom("chr1") == "1"
    assert mane_mod._ensembl_chrom("chrX") == "X"
    assert mane_mod._ensembl_chrom("chrM") == "MT"
    assert mane_mod._ensembl_chrom("chrMT") == "MT"
    assert mane_mod._ensembl_chrom("M") == "MT"
    assert mane_mod._ensembl_chrom("17") == "17"


# ---------------------------------------------------------------------------
# MANE local GFF3 — MANE_Select tag selection
# ---------------------------------------------------------------------------

_FAKE_GFF3 = "\n".join([
    "##gff-version 3",
    # gene 1: Plus Clinical listed FIRST, MANE Select second
    "1\tBestRefSeq\tgene\t1000\t5000\t.\t+\t.\tID=gene:ENSG00000000001.2;gene_id=ENSG00000000001.2;Name=FAKE1",
    "1\tBestRefSeq\tmRNA\t1000\t5000\t.\t+\t.\tID=transcript:ENST00000000002.1;Parent=gene:ENSG00000000001.2;gene_id=ENSG00000000001.2;transcript_id=ENST00000000002.1;tag=MANE_Plus_Clinical",
    "1\tBestRefSeq\texon\t1000\t1200\t.\t+\t.\tParent=transcript:ENST00000000002.1",
    "1\tBestRefSeq\texon\t2000\t2200\t.\t+\t.\tParent=transcript:ENST00000000002.1",
    "1\tBestRefSeq\tCDS\t1100\t1200\t.\t+\t.\tParent=transcript:ENST00000000002.1",
    "1\tBestRefSeq\tmRNA\t1000\t5000\t.\t+\t.\tID=transcript:ENST00000000001.1;Parent=gene:ENSG00000000001.2;gene_id=ENSG00000000001.2;transcript_id=ENST00000000001.1;tag=basic,MANE_Select",
    "1\tBestRefSeq\texon\t1000\t1300\t.\t+\t.\tParent=transcript:ENST00000000001.1",
    "1\tBestRefSeq\texon\t3000\t3300\t.\t+\t.\tParent=transcript:ENST00000000001.1",
    "1\tBestRefSeq\tCDS\t1100\t1300\t.\t+\t.\tParent=transcript:ENST00000000001.1",
    # gene 2: no tag attribute at all → fallback to first transcript seen
    "2\tBestRefSeq\tgene\t100\t900\t.\t-\t.\tID=gene:ENSG00000000009.1;gene_id=ENSG00000000009.1;Name=FAKE2",
    "2\tBestRefSeq\tmRNA\t100\t900\t.\t-\t.\tID=transcript:ENST00000000009.1;Parent=gene:ENSG00000000009.1;gene_id=ENSG00000000009.1;transcript_id=ENST00000000009.1",
    "2\tBestRefSeq\texon\t100\t300\t.\t-\t.\tParent=transcript:ENST00000000009.1",
    "",
])


@pytest.fixture
def fake_mane_gff3(tmp_path):
    path = tmp_path / "MANE.GRCh38.vtest.ensembl_genomic.gff.gz"
    with gzip.open(path, "wt") as fh:
        fh.write(_FAKE_GFF3)
    mane_local._reset_index()
    yield path
    mane_local._reset_index()


def test_mane_local_selects_mane_select_tag_not_file_order(fake_mane_gff3):
    assert mane_local.load_mane_gff3(fake_mane_gff3) is True
    assert mane_local.is_loaded()

    data = mane_local.get_mane_for_gene("ENSG00000000001")
    assert data is not None
    assert data["transcript_id"] == "ENST00000000001"
    assert data["is_mane_select"] is True
    assert "MANE_Select" in data["tags"]
    # versioned gene id also resolves
    assert mane_local.get_mane_for_gene("ENSG00000000001.2")["transcript_id"] == "ENST00000000001"
    # exons parsed and 0-based
    assert data["exons"] == [{"start": 999, "end": 1300}, {"start": 2999, "end": 3300}]

    plus = mane_local.get_mane_plus_clinical("ENSG00000000001")
    assert [t["transcript_id"] for t in plus] == ["ENST00000000002"]
    assert mane_local.get_mane_plus_clinical("ENSG00000000009") == []

    # both transcripts remain reachable by id
    assert mane_local.get_transcript_exons_local("ENST00000000002")[0]["size"] == 201

    # gene without any tag falls back to the first transcript seen
    fb = mane_local.get_mane_for_gene("ENSG00000000009")
    assert fb is not None and fb["transcript_id"] == "ENST00000000009"
    assert fb["is_mane_select"] is False


def test_mane_local_annotate_uses_mane_select_exons(fake_mane_gff3):
    assert mane_local.load_mane_gff3(fake_mane_gff3)
    # exon [2999, 3300) is exon 2 of the MANE Select transcript only
    r = mane_local.annotate_from_local("ENSG00000000001", 2999, 3300)
    assert r["transcript_id"] == "ENST00000000001"
    assert r["exon_rank"] == 2
    b = mane_local.get_mane_exon_boundaries("ENSG00000000001", 2990, 3310)
    assert b == (2999, 3300, "overlap")


def test_parse_tags():
    assert mane_local._parse_tags("MANE_Select") == {"MANE_Select"}
    assert mane_local._parse_tags("basic,MANE_Select") == {"basic", "MANE_Select"}
    assert mane_local._parse_tags("basic%2CMANE_Plus_Clinical") == {"basic", "MANE_Plus_Clinical"}
    assert mane_local._parse_tags("") == set()
