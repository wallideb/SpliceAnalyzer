"""
Tests for app.services.hnrnp_motifs: seven-region SE definition (rMAPS2 design),
motif scanning with per-event densities, presence/density tests and BH.

Run:  python -m pytest tests/test_hnrnp_motifs.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import hnrnp_motifs as hm
from app.services.hnrnp_motifs import (
    HNRNP_MOTIFS,
    REGION_NAMES,
    REGULATORY_EFFECTS,
    MotifRegionResult,
    SERegions,
    _bh_adjust,
    _mann_whitney_u,
    _proportion_z_test,
    compare_groups,
    define_se_regions,
    scan_group,
)

CHR = "chr1"
EMPTY = (CHR, 0, 0)


def _regions(strand: str, intron_len: int) -> dict[str, tuple[str, int, int]]:
    """SE event with 300-nt flanking exons, a 200-nt skipped exon and two
    introns of `intron_len` nt, starting at genomic position 10_000."""
    up_es = 10_000
    up_ee = up_es + 300
    ex_s = up_ee + intron_len
    ex_e = ex_s + 200
    dn_es = ex_e + intron_len
    dn_ee = dn_es + 300
    bed = define_se_regions(CHR, strand, ex_s, ex_e, up_es, up_ee, dn_es, dn_ee)
    assert len(bed) == len(REGION_NAMES) == 7
    return dict(zip(REGION_NAMES, bed))


# ---------------------------------------------------------------------------
# Region definitions
# ---------------------------------------------------------------------------

def test_region_names_contract():
    assert REGION_NAMES == [
        "upstream_exon", "upstream_intron_5ss", "upstream_intron_3ss",
        "skipped_exon", "downstream_intron_5ss", "downstream_intron_3ss",
        "downstream_exon",
    ]
    assert [f for f in SERegions.__dataclass_fields__] == REGION_NAMES
    for _, protein, _ in HNRNP_MOTIFS:
        assert set(REGULATORY_EFFECTS[protein]) == set(REGION_NAMES)


def test_plus_strand_long_intron_windows_are_disjoint():
    r = _regions("+", 1000)
    up_ee, ex_s, ex_e, dn_es = 10_300, 11_300, 11_500, 12_500
    assert r["upstream_exon"] == (CHR, up_ee - 250, up_ee)
    assert r["upstream_intron_5ss"] == (CHR, up_ee + 6, up_ee + 6 + 250)
    assert r["upstream_intron_3ss"] == (CHR, ex_s - 20 - 250, ex_s - 20)
    assert r["skipped_exon"] == (CHR, ex_s, ex_e)
    assert r["downstream_intron_5ss"] == (CHR, ex_e + 6, ex_e + 6 + 250)
    assert r["downstream_intron_3ss"] == (CHR, dn_es - 20 - 250, dn_es - 20)
    assert r["downstream_exon"] == (CHR, dn_es, dn_es + 250)
    # 5'SS and 3'SS windows of the same intron do not overlap in a 1000-nt intron
    assert r["upstream_intron_5ss"][2] <= r["upstream_intron_3ss"][1]
    assert r["downstream_intron_5ss"][2] <= r["downstream_intron_3ss"][1]


def test_plus_strand_short_intron_windows_overlap_and_are_clipped():
    r = _regions("+", 300)
    up_ee, ex_s, ex_e, dn_es = 10_300, 10_600, 10_800, 11_100
    # 300-nt intron: body after exclusions is [lo+6, hi-20) = 274 nt
    assert r["upstream_intron_5ss"] == (CHR, up_ee + 6, up_ee + 256)
    assert r["upstream_intron_3ss"] == (CHR, ex_s - 270, ex_s - 20)
    assert r["downstream_intron_5ss"] == (CHR, ex_e + 6, ex_e + 256)
    assert r["downstream_intron_3ss"] == (CHR, dn_es - 270, dn_es - 20)
    # Both windows are 250 nt and share 226 nt (documented overlap)
    for name in ("upstream_intron", "downstream_intron"):
        five, three = r[f"{name}_5ss"], r[f"{name}_3ss"]
        assert five[2] - five[1] == 250 and three[2] - three[1] == 250
        assert five[1] < three[1] < five[2] < three[2]
        assert five[2] - three[1] == 226
    # Every window stays inside the intron body minus the exclusion zones
    assert r["upstream_intron_3ss"][1] >= up_ee + 6
    assert r["downstream_intron_3ss"][1] >= ex_e + 6


def test_plus_strand_20nt_intron_gives_empty_windows():
    r = _regions("+", 20)
    for name in ("upstream_intron_5ss", "upstream_intron_3ss",
                 "downstream_intron_5ss", "downstream_intron_3ss"):
        assert r[name] == EMPTY
    assert r["skipped_exon"] == (CHR, 10_320, 10_520)
    assert r["upstream_exon"] == (CHR, 10_050, 10_300)


def test_minus_strand_long_intron_is_mirror_image():
    r = _regions("-", 1000)
    up_es, up_ee, ex_s, ex_e, dn_es, dn_ee = 10_000, 10_300, 11_300, 11_500, 12_500, 12_800
    # Transcript upstream exon = rMATS downstream exon, intron-proximal end at dn_es
    assert r["upstream_exon"] == (CHR, dn_es, dn_es + 250)
    # Transcript upstream intron = genomic [ex_e, dn_es): 5'SS at dn_es, 3'SS at ex_e
    assert r["upstream_intron_5ss"] == (CHR, dn_es - 6 - 250, dn_es - 6)
    assert r["upstream_intron_3ss"] == (CHR, ex_e + 20, ex_e + 20 + 250)
    assert r["skipped_exon"] == (CHR, ex_s, ex_e)
    # Transcript downstream intron = genomic [up_ee, ex_s): 5'SS at ex_s, 3'SS at up_ee
    assert r["downstream_intron_5ss"] == (CHR, ex_s - 6 - 250, ex_s - 6)
    assert r["downstream_intron_3ss"] == (CHR, up_ee + 20, up_ee + 20 + 250)
    # Transcript downstream exon = rMATS upstream exon, intron-proximal end at up_ee
    assert r["downstream_exon"] == (CHR, up_ee - 250, up_ee)
    assert up_es == 10_000 and dn_ee == 12_800


def test_minus_strand_short_intron_overlap():
    r = _regions("-", 300)
    up_ee, ex_s, ex_e, dn_es = 10_300, 10_600, 10_800, 11_100
    assert r["upstream_intron_5ss"] == (CHR, dn_es - 256, dn_es - 6)
    assert r["upstream_intron_3ss"] == (CHR, ex_e + 20, ex_e + 270)
    assert r["downstream_intron_5ss"] == (CHR, ex_s - 256, ex_s - 6)
    assert r["downstream_intron_3ss"] == (CHR, up_ee + 20, up_ee + 270)
    for name in ("upstream_intron", "downstream_intron"):
        five, three = r[f"{name}_5ss"], r[f"{name}_3ss"]
        assert five[2] - five[1] == 250 and three[2] - three[1] == 250
        assert three[1] < five[1] < three[2] < five[2]


def test_minus_strand_20nt_intron_gives_empty_windows():
    r = _regions("-", 20)
    for name in ("upstream_intron_5ss", "upstream_intron_3ss",
                 "downstream_intron_5ss", "downstream_intron_3ss"):
        assert r[name] == EMPTY


def test_plus_and_minus_windows_cover_identical_nucleotides():
    """The set of scanned intronic positions is strand-independent up to the
    swap of roles (5'SS ↔ 3'SS side of each intron)."""
    plus = _regions("+", 600)
    minus = _regions("-", 600)
    # intron A = [10300, 10900): + 5ss window == − downstream 3ss window mirrored
    assert plus["upstream_intron_5ss"] == (CHR, 10_306, 10_556)
    assert minus["downstream_intron_3ss"] == (CHR, 10_320, 10_570)
    assert plus["upstream_intron_3ss"] == (CHR, 10_630, 10_880)
    assert minus["downstream_intron_5ss"] == (CHR, 10_644, 10_894)


def test_missing_flanking_coordinates_yield_empty_regions():
    bed = define_se_regions(CHR, "+", 1000, 1200, None, None, None, None)
    assert bed[3] == (CHR, 1000, 1200)
    assert all(b == EMPTY for i, b in enumerate(bed) if i != 3)
    bed = define_se_regions(CHR, "-", 1000, 1200, 100, 400, None, None)
    d = dict(zip(REGION_NAMES, bed))
    assert d["upstream_exon"] == EMPTY
    assert d["upstream_intron_5ss"] == EMPTY and d["upstream_intron_3ss"] == EMPTY
    assert d["downstream_exon"] == (CHR, 150, 400)
    assert d["downstream_intron_5ss"] == (CHR, 1000 - 256, 994)
    assert d["downstream_intron_3ss"] == (CHR, 420, 670)


def test_short_flanking_exon_is_taken_whole():
    bed = define_se_regions(CHR, "+", 5000, 5100, 4000, 4050, 6000, 6030)
    d = dict(zip(REGION_NAMES, bed))
    assert d["upstream_exon"] == (CHR, 4000, 4050)
    assert d["downstream_exon"] == (CHR, 6000, 6030)


# ---------------------------------------------------------------------------
# scan_group
# ---------------------------------------------------------------------------

def _lookup(results: list[MotifRegionResult], motif: str, region: str) -> MotifRegionResult:
    return next(r for r in results if r.motif_name == motif and r.region == region)


def test_scan_group_counts_and_densities():
    ev1 = SERegions(skipped_exon="TAGGTAGG", upstream_intron_3ss="ACGTACGT")   # TAGG ×2 → 8/8
    ev2 = SERegions(skipped_exon="AAAATAGGAA")                                  # TAGG ×1 → 4/10
    ev3 = SERegions(skipped_exon="CCCCCCCCCC")                                  # no TAGG
    ev4 = SERegions()                                                           # all empty
    res = scan_group([ev1, ev2, ev3, ev4])
    assert len(res) == len(HNRNP_MOTIFS) * len(REGION_NAMES)

    r = _lookup(res, "TAGG", "skipped_exon")
    assert r.total_events == 3            # ev4 has an empty skipped exon
    assert r.count_events_with_hit == 2
    assert r.densities == [1.0, 0.4, 0.0]
    assert r.mean_density == pytest.approx((1.0 + 0.4 + 0.0) / 3)

    # Overlapping occurrences are counted (CCCC in C10 → 7 overlapping hits, capped at 1)
    r = _lookup(res, "CCCC", "skipped_exon")
    assert r.densities == [0.0, 0.0, 1.0]

    # Only ev1 provides the upstream_intron_3ss region
    r = _lookup(res, "ACAC", "upstream_intron_3ss")
    assert r.total_events == 1 and r.densities == [0.0]
    r = _lookup(res, "AGG", "upstream_intron_3ss")
    assert r.count_events_with_hit == 0

    # Regions never provided have no events at all
    r = _lookup(res, "TAGG", "downstream_intron_5ss")
    assert r.total_events == 0 and r.densities == [] and r.mean_density == 0.0


def test_scan_group_degenerate_motif():
    res = scan_group([SERegions(downstream_exon="CCATACC")])   # CC[AT][AT][ACT]CC
    r = _lookup(res, "CCWWHCC", "downstream_exon")
    assert r.count_events_with_hit == 1 and r.densities == [1.0]
    r = _lookup(res, "CCYYCCH", "downstream_exon")
    assert r.count_events_with_hit == 0 and r.densities == [0.0]


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def test_proportion_z_test_small_group_guard():
    assert _proportion_z_test(3, 4, 1, 100) == (None, None)
    assert _proportion_z_test(30, 100, 1, 4) == (None, None)
    z, p = _proportion_z_test(4, 5, 1, 5)
    assert z is not None and p is not None and 0 < p < 1
    assert _proportion_z_test(0, 10, 0, 10) == (None, None)   # pooled p = 0
    assert _proportion_z_test(10, 10, 10, 10) == (None, None)  # pooled p = 1
    z, p = _proportion_z_test(80, 100, 20, 100)
    assert z == pytest.approx(8.4853, abs=1e-3) and p < 1e-10


def test_mann_whitney_known_vectors():
    u, p = _mann_whitney_u([1, 2, 3, 4, 5], [6, 7, 8, 9, 10])
    assert u == 0.0
    # scipy mannwhitneyu(method="asymptotic", use_continuity=True) → 0.01218
    assert p == pytest.approx(0.01218, abs=1e-3)
    u2, p2 = _mann_whitney_u([6, 7, 8, 9, 10], [1, 2, 3, 4, 5])
    assert u2 == 25.0 and p2 == pytest.approx(p)          # symmetric
    u, p = _mann_whitney_u([0.1, 0.2, 0.3, 0.4, 0.5, 0.6], [0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    assert u == pytest.approx(18.0) and p == pytest.approx(1.0)
    # All values tied → zero variance → test undefined (U reported, p None),
    # so the pair is not counted in the BH family (same as the z-test)
    assert _mann_whitney_u([0.0] * 6, [0.0] * 8) == (24.0, None)
    # Small-group guard
    assert _mann_whitney_u([1, 2, 3, 4], [5, 6, 7, 8, 9]) == (None, None)
    assert _mann_whitney_u([], [1, 2, 3, 4, 5]) == (None, None)


def test_mann_whitney_tie_correction_matches_reference():
    # By hand: U_a = #(a_i > b_j) + 0.5 #(a_i = b_j) = 9; tie blocks of size
    # 2,3,4,3,2 give sum(t^3 - t) = 120, var = 49/12 * (15 - 120/182) = 58.558,
    # with the 0.5 continuity correction z = (9 - 24.5 + 0.5) / sqrt(var)
    # = -1.9602, two-sided p = 0.04997 (R wilcox.test / scipy use_continuity=True)
    a = [1, 1, 2, 2, 3, 3, 4]
    b = [2, 3, 3, 4, 4, 5, 5]
    u, p = _mann_whitney_u(a, b)
    assert u == pytest.approx(9.0)
    assert p == pytest.approx(0.04997, abs=5e-4)
    # Ranks ignore scale: the result is identical after a monotone transform
    u_t, p_t = _mann_whitney_u([x * 100 for x in a], [x * 100 for x in b])
    assert u_t == u and p_t == pytest.approx(p)


def test_bh_adjust_monotone_and_bounded():
    p = [0.01, 0.04, 0.03, 0.20, 0.5, 0.0005, 0.9]
    q = _bh_adjust(p)
    assert len(q) == len(p)
    assert all(0 <= qi <= 1 for qi in q)
    assert all(qi >= pi for qi, pi in zip(q, p))
    # Monotone in the raw p ordering
    order = sorted(range(len(p)), key=lambda i: p[i])
    for a, b in zip(order, order[1:]):
        assert q[a] <= q[b]
    # Known values: smallest p × n / 1, largest is unchanged
    assert q[5] == pytest.approx(0.0005 * 7)
    assert q[6] == pytest.approx(0.9)
    assert _bh_adjust([]) == []
    assert _bh_adjust([0.2]) == [0.2]


# ---------------------------------------------------------------------------
# compare_groups
# ---------------------------------------------------------------------------

def _region_result(motif: str, region: str, densities: list[float]) -> MotifRegionResult:
    protein = next(p for m, p, _ in HNRNP_MOTIFS if m == motif)
    hits = sum(1 for d in densities if d > 0)
    n = len(densities)
    return MotifRegionResult(
        motif_name=motif, protein=protein, region=region,
        count_events_with_hit=hits, total_events=n,
        mean_density=sum(densities) / n if n else 0.0, densities=list(densities),
    )


def test_compare_groups_small_group_guard_and_untestable():
    sig = [_region_result("TAGG", "skipped_exon", [1.0, 0.5, 0.0, 0.2])]          # n = 4
    bg = [_region_result("TAGG", "skipped_exon", [0.0] * 10 + [0.3] * 10)]
    out = compare_groups(sig, bg)
    assert len(out) == 1
    r = out[0]
    assert r.sig_total == 4 and r.bg_total == 20
    assert r.z_stat is None and r.p_value is None and r.p_adjusted is None
    assert r.significant is False
    assert r.density_u_stat is None and r.density_p_value is None
    assert r.density_p_adjusted is None and r.density_significant is False

    # A pair missing from the background is skipped
    sig.append(_region_result("GGG", "upstream_exon", [0.0] * 5))
    assert len(compare_groups(sig, bg)) == 1


def test_compare_groups_presence_and_density_families():
    sig_present = [1.0] * 10 + [0.0] * 0
    bg_absent = [0.0] * 10
    # Both tests detect the difference in pair A
    sig = [_region_result("TAGG", "skipped_exon", sig_present)]
    bg = [_region_result("TAGG", "skipped_exon", bg_absent)]
    # Pair B: presence saturates (every event has a hit) but density differs
    sig.append(_region_result("AGG", "upstream_intron_5ss", [0.9] * 10))
    bg.append(_region_result("AGG", "upstream_intron_5ss", [0.1] * 10))
    # Pair C: identical groups
    sig.append(_region_result("GGG", "downstream_exon", [0.2, 0.0, 0.4, 0.0, 0.6]))
    bg.append(_region_result("GGG", "downstream_exon", [0.2, 0.0, 0.4, 0.0, 0.6]))
    out = {(r.motif_name, r.region): r for r in compare_groups(sig, bg)}
    assert len(out) == 3

    a = out[("TAGG", "skipped_exon")]
    assert a.p_value is not None and a.p_value < 0.001
    assert a.significant and a.density_significant
    assert a.density_u_stat == 100.0
    assert a.sig_density == 1.0 and a.bg_density == 0.0

    b = out[("AGG", "upstream_intron_5ss")]
    assert b.z_stat is None and b.p_value is None and b.significant is False   # pooled p = 1
    assert b.density_p_value is not None and b.density_p_value < 0.001
    assert b.density_significant

    c = out[("GGG", "downstream_exon")]
    assert c.p_value == pytest.approx(1.0) and c.density_p_value == pytest.approx(1.0)
    assert not c.significant and not c.density_significant

    # BH is applied per family over the testable pairs only (2 presence, 3 density)
    assert a.p_adjusted == pytest.approx(min(1.0, a.p_value * 2), abs=2e-6)
    assert c.p_adjusted == pytest.approx(1.0)
    assert a.density_p_adjusted is not None and a.density_p_adjusted >= a.density_p_value
    assert c.density_p_adjusted == pytest.approx(1.0)
    for r in out.values():
        for v in (r.p_value, r.p_adjusted, r.density_p_value, r.density_p_adjusted):
            if v is not None:
                assert 0.0 <= v <= 1.0 and v == round(v, 6)


def test_compare_groups_end_to_end_with_scan_group():
    """Regions produced by scan_group feed compare_groups without adaptation."""
    sig = [SERegions(skipped_exon="TAGG" * 10, upstream_intron_3ss="TTTTT" * 5) for _ in range(6)]
    bg = [SERegions(skipped_exon="ACGT" * 10, upstream_intron_3ss="ACGAC" * 5) for _ in range(6)]
    out = compare_groups(scan_group(sig), scan_group(bg))
    by_key = {(r.motif_name, r.region): r for r in out}
    tagg = by_key[("TAGG", "skipped_exon")]
    assert tagg.sig_hit_count == 6 and tagg.bg_hit_count == 0
    assert tagg.p_value is not None and tagg.density_p_value is not None
    tttt = by_key[("TTTTT", "upstream_intron_3ss")]
    assert tttt.sig_density == 1.0 and tttt.bg_density == 0.0
    # Regions with no sequences at all are untestable, not errors
    empty = by_key[("TAGG", "downstream_intron_5ss")]
    assert empty.sig_total == 0 and empty.p_value is None and empty.density_p_value is None


def test_dead_helpers_removed():
    assert not hasattr(hm, "count_motif_occurrences")
    assert not hasattr(hm, "motif_density")


def test_stats_helpers_are_shared_with_deep_analyses_router():
    """D18: one implementation of z / U / BH for the router and the motif module."""
    from app.routers import deep_analyses as da
    from app.services import stats
    assert da._mann_whitney_u is hm._mann_whitney_u is stats.mann_whitney_u
    assert da._proportion_z_test is hm._proportion_z_test is stats.proportion_z_test
    assert da._normal_cdf is hm._normal_cdf is stats.normal_cdf
    assert da._bh_adjust is stats.bh_adjust and hm._bh_adjust_optional is stats.bh_adjust
    a = [0.1, 0.0, 0.3, 0.0, 0.2, 0.5, 0.0]
    b = [0.0, 0.0, 0.1, 0.0, 0.0, 0.05]
    assert da._mann_whitney_u(a, b) == hm._mann_whitney_u(a, b)
    assert da._proportion_z_test(7, 20, 3, 25) == hm._proportion_z_test(7, 20, 3, 25)


def test_build_se_regions_batches_and_orients(monkeypatch):
    """build_se_regions asks for 7 regions per event in REGION_NAMES order and
    reverse-complements − strand sequences; events without coordinates get
    seven empty regions."""
    from types import SimpleNamespace as NS
    captured: dict = {}

    def fake_extract(regions, fasta_path=None, progress=None):
        captured["regions"] = list(regions)
        out = []
        for chrom, s, e in regions:
            out.append("" if e <= s else ("ACGT" * ((e - s) // 4 + 1))[: e - s])
        return out

    monkeypatch.setattr(hm, "extract_regions_batch", fake_extract)
    plus = NS(chr=CHR, strand="+", exon_start=1000, exon_end=1100,
              upstream_es=500, upstream_ee=600, downstream_es=1500, downstream_ee=1600)
    minus = NS(chr=CHR, strand="-", exon_start=1000, exon_end=1100,
               upstream_es=500, upstream_ee=600, downstream_es=1500, downstream_ee=1600)
    none = NS(chr=None, strand="+", exon_start=None, exon_end=None,
              upstream_es=None, upstream_ee=None, downstream_es=None, downstream_ee=None)
    out = hm.build_se_regions([plus, minus, none], fasta_path="/dev/null", label="t")
    assert len(out) == 3
    n = len(REGION_NAMES)
    assert len(captured["regions"]) == 3 * n
    assert captured["regions"][:n] == define_se_regions(CHR, "+", 1000, 1100, 500, 600, 1500, 1600)
    assert captured["regions"][n:2 * n] == define_se_regions(CHR, "-", 1000, 1100, 500, 600, 1500, 1600)
    assert captured["regions"][2 * n:] == [("", 0, 0)] * n
    # + strand: sequence as fetched; − strand: reverse complement of the fetch
    assert out[0].skipped_exon == ("ACGT" * 26)[:100]
    assert out[1].skipped_exon == hm.reverse_complement(("ACGT" * 26)[:100])
    assert all(getattr(out[2], r) == "" for r in REGION_NAMES)
