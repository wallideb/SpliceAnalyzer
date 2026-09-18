"""
Tests for app.services.permutation: exact enumeration for small designs,
Monte-Carlo (Phipson-Smyth) for large ones, observed ΔΨ source and the
accumulated global null histogram.

Run:  python -m pytest tests/test_permutation.py -v
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.permutation import (
    _hist_counts,
    _make_histogram,
    _run_metric_permutation,
    _split_masks,
    run_permutation,
)
import random


@dataclass
class FakeEvent:
    id: str
    inc_level_1: str | None
    inc_level_2: str | None
    inc_level_difference: float | None = None
    event_type: str = "SE"
    gene_symbol: str | None = "GENE"
    analysis_id: str = "analysis-1"


@dataclass
class FakeFeature:
    ppt_score: float | None = None
    exon_size: int | None = None
    frame_class: str | None = None
    donor_is_gt: bool | None = None
    acceptor_is_ag: bool | None = None


def _events(n_events: int, n1: int, n2: int, seed: int = 0) -> list[FakeEvent]:
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n_events):
        p1 = rng.uniform(0.5, 1.0, n1)
        p2 = rng.uniform(0.0, 0.5, n2)
        out.append(FakeEvent(
            id=f"ev{i}",
            inc_level_1=",".join(f"{v:.3f}" for v in p1),
            inc_level_2=",".join(f"{v:.3f}" for v in p2),
            inc_level_difference=round(float(p1.mean() - p2.mean()), 3),
        ))
    return out


# ---------------------------------------------------------------------------
# Exact enumeration
# ---------------------------------------------------------------------------

def test_2v2_design_is_exact_with_6_splits():
    evs = _events(8, 2, 2)
    res = run_permutation(evs, [None] * len(evs), n_iterations=500)
    assert res.n_events_tested == 8
    assert res.exact_fraction == 1.0
    assert res.n_replicates_g1 == 2 and res.n_replicates_g2 == 2
    assert res.min_p_attainable == pytest.approx(1 / 6)
    for r in res.events:
        assert r.exact is True and r.n_splits == 6
        assert r.n1 == 2 and r.n2 == 2
        k = r.empirical_p_value * 6
        assert k == pytest.approx(round(k), abs=1e-3)      # p ∈ {k/6}
        assert 1 <= round(k) <= 6
        assert sum(r.null_hist_counts) == 6                  # per-event null = all splits
    # Global null histogram accumulates every enumerated split
    assert sum(res.global_null_hist_counts) == 8 * 6
    assert len(res.global_null_hist_bins) == 40
    assert res.global_null_hist_bins[0] == -1.0 and res.global_null_hist_bins[-1] == pytest.approx(0.95)


def test_exact_p_value_counts_the_observed_split():
    # Groups perfectly separated: only the observed split and its mirror reach |ΔΨ| = 0.7
    ev = FakeEvent("e", "0.9,0.8", "0.1,0.2", inc_level_difference=0.7)
    res = run_permutation([ev], [None], n_iterations=10)
    r = res.events[0]
    assert r.exact and r.n_splits == 6
    assert r.empirical_p_value == pytest.approx(2 / 6, abs=1e-4)
    assert r.observed_delta_psi == 0.7
    # Both groups identical → every split gives the same |ΔΨ| → p = 1
    ev = FakeEvent("f", "0.5,0.5", "0.5,0.5", inc_level_difference=0.0)
    r = run_permutation([ev], [None], n_iterations=10).events[0]
    assert r.empirical_p_value == 1.0


def test_3v3_design_has_20_splits():
    evs = _events(5, 3, 3)
    res = run_permutation(evs, [None] * 5, n_iterations=500)
    assert res.min_p_attainable == pytest.approx(1 / 20)
    for r in res.events:
        assert r.exact and r.n_splits == 20
        k = r.empirical_p_value * 20
        assert k == pytest.approx(round(k), abs=1e-2)
        assert r.empirical_p_value >= 1 / 20
    assert sum(res.global_null_hist_counts) == 5 * 20


def test_exact_path_is_seed_independent():
    evs = _events(4, 3, 2)
    a = run_permutation(evs, [None] * 4, seed=1)
    b = run_permutation(evs, [None] * 4, seed=None)
    assert [r.empirical_p_value for r in a.events] == [r.empirical_p_value for r in b.events]
    assert a.global_null_hist_counts == b.global_null_hist_counts


def test_split_masks_enumerate_all_distinct_splits_with_observed_first():
    m = _split_masks(2, 3)
    assert m.shape == (math.comb(5, 2), 5)
    assert m.sum(axis=1).tolist() == [2] * 10
    assert m[0].tolist() == [True, True, False, False, False]
    assert len({tuple(row) for row in m.tolist()}) == 10


# ---------------------------------------------------------------------------
# Monte-Carlo path
# ---------------------------------------------------------------------------

def test_10v10_design_uses_monte_carlo():
    evs = _events(6, 10, 10)
    k = 200
    res = run_permutation(evs, [None] * 6, n_iterations=k)
    assert res.exact_fraction == 0.0
    assert res.n_replicates_g1 == 10 and res.n_replicates_g2 == 10
    assert res.min_p_attainable == pytest.approx(1 / (k + 1))
    for r in res.events:
        assert r.exact is False and r.n_splits is None
        assert r.empirical_p_value >= 1 / (k + 1) - 1e-9
        assert sum(r.null_hist_counts) == k
    assert sum(res.global_null_hist_counts) == 6 * k
    # Well-separated groups: the observed |ΔΨ| is rarely reached by chance
    assert res.pct_p05 is not None and res.pct_p05 > 50


def test_monte_carlo_is_reproducible_with_seed():
    evs = _events(3, 10, 10)
    a = run_permutation(evs, [None] * 3, n_iterations=100, seed=7)
    b = run_permutation(evs, [None] * 3, n_iterations=100, seed=7)
    c = run_permutation(evs, [None] * 3, n_iterations=100, seed=8)
    assert a.global_null_hist_counts == b.global_null_hist_counts
    assert a.global_null_hist_counts != c.global_null_hist_counts


def test_exact_max_splits_switches_path():
    evs = _events(3, 2, 2)
    res = run_permutation(evs, [None] * 3, n_iterations=50, exact_max_splits=0)
    assert res.exact_fraction == 0.0
    assert res.min_p_attainable == pytest.approx(1 / 51)
    for r in res.events:
        assert r.exact is False and r.n_splits is None
        assert r.empirical_p_value >= 1 / 51 - 1e-9
    assert sum(res.global_null_hist_counts) == 3 * 50


def test_mixed_designs_report_mode_and_fraction():
    evs = _events(3, 2, 2) + _events(2, 10, 10, seed=1)
    for i, ev in enumerate(evs):
        ev.id = f"mix{i}"
    res = run_permutation(evs, [None] * 5, n_iterations=100)
    assert res.exact_fraction == pytest.approx(3 / 5)
    assert (res.n_replicates_g1, res.n_replicates_g2) == (2, 2)
    assert res.min_p_attainable == pytest.approx(1 / 6)
    assert sum(res.global_null_hist_counts) == 3 * 6 + 2 * 100


# ---------------------------------------------------------------------------
# Observed ΔΨ source and skipped events
# ---------------------------------------------------------------------------

def test_observed_delta_comes_from_inc_level_difference_when_present():
    ev = FakeEvent("a", "0.9,0.8,NA", "0.1,0.2,0.3", inc_level_difference=0.123)
    r = run_permutation([ev], [None]).events[0]
    assert r.observed_delta_psi == 0.123
    assert r.n1 == 2 and r.n2 == 3
    # Fallback when rMATS did not provide it: mean(psi1) - mean(psi2)
    ev = FakeEvent("b", "0.9,0.8", "0.1,0.2", inc_level_difference=None)
    r = run_permutation([ev], [None]).events[0]
    assert r.observed_delta_psi == pytest.approx(0.7)


def test_events_without_valid_psi_or_non_se_are_skipped():
    evs = [
        FakeEvent("ok", "0.9,0.8", "0.1,0.2", 0.7),
        FakeEvent("na1", "NA,NA", "0.1,0.2", 0.7),
        FakeEvent("na2", "0.9,0.8", None, 0.7),
        FakeEvent("mxe", "0.9,0.8", "0.1,0.2", 0.7, event_type="MXE"),
    ]
    res = run_permutation(evs, [None] * 4)
    assert [r.event_id for r in res.events] == ["ok"]
    assert res.n_events_tested == 1
    res = run_permutation(evs, [None] * 4, only_se=False)
    assert [r.event_id for r in res.events] == ["ok", "mxe"]
    empty = run_permutation([], [])
    assert empty.n_events_tested == 0 and empty.global_null_hist_counts == []
    assert empty.min_p_attainable is None and empty.n_replicates_g1 is None
    assert empty.exact_fraction == 0.0 and empty.pct_p05 is None


# ---------------------------------------------------------------------------
# Histograms
# ---------------------------------------------------------------------------

def test_histogram_helpers_agree_and_cover_all_values():
    vals = [-1.0, -0.999, -0.5, 0.0, 0.024, 0.025, 0.5, 0.999, 1.0, 1.5, -2.0]
    bins, counts = _make_histogram(vals, n_bins=40)
    assert len(bins) == 40 and len(counts) == 40
    assert sum(counts) == len(vals)                     # out-of-range values clipped to edge bins
    assert counts == _hist_counts(np.array(vals), 40, -1.0, 1.0).tolist()
    assert bins[0] == -1.0 and bins[20] == 0.0
    assert counts[20] == 3                              # 0.0, 0.024, 0.025 fall in [0, 0.05)
    assert counts[30] == 1                              # 0.5
    assert counts[0] == 3                               # -1.0, -0.999, -2.0
    assert counts[39] == 3                              # 0.999, 1.0 (clipped), 1.5 (clipped)
    assert _make_histogram([]) == ([], [])


# ---------------------------------------------------------------------------
# Scalar metric permutation
# ---------------------------------------------------------------------------

def test_metric_permutation_exact_when_small():
    rng = random.Random(0)
    r = _run_metric_permutation([1.0, 2.0, 3.0], [4.0, 5.0, 6.0], 500, rng, "m", "M", lo=-10, hi=10)
    assert r.exact and r.n_splits == 20
    assert r.observed_stat == pytest.approx(3.0)        # mean(G2) - mean(G1)
    assert r.empirical_p_value == pytest.approx(2 / 20)  # only the two extreme splits
    assert r.n_g1 == 3 and r.n_g2 == 3 and r.n_valid == 6
    assert sum(r.null_hist_counts) == 20
    # Too few values → untested
    r = _run_metric_permutation([1.0], [2.0, 3.0], 500, rng, "m", "M")
    assert r.empirical_p_value is None and r.exact is False and r.n_splits is None


def test_metric_permutation_monte_carlo_when_large():
    rng = random.Random(0)
    g1 = [float(i) for i in range(30)]
    g2 = [float(i) + 5 for i in range(30)]
    r = _run_metric_permutation(g1, g2, 300, rng, "m", "M", lo=-40, hi=40)
    assert not r.exact and r.n_splits is None
    assert r.observed_stat == pytest.approx(5.0)
    assert r.empirical_p_value >= 1 / 301 - 1e-9
    assert sum(r.null_hist_counts) == 300


def test_run_permutation_metric_results_from_features():
    evs = _events(12, 3, 3)
    feats = []
    for i, ev in enumerate(evs):
        # Alternate sign so both metric groups are populated
        ev.inc_level_difference = 0.5 if i % 2 else -0.5
        feats.append(FakeFeature(
            ppt_score=0.5 + 0.02 * i, exon_size=100 + 10 * i,
            frame_class="in_frame" if i % 3 else "frameshift",
            donor_is_gt=True, acceptor_is_ag=bool(i % 2),
        ))
    res = run_permutation(evs, feats, n_iterations=100)
    names = [m.metric_name for m in res.metric_results]
    assert names == ["ppt_score", "exon_size", "frame_in_frame", "canonical_sites"]
    for m in res.metric_results:
        assert m.n_g1 == 6 and m.n_g2 == 6 and m.n_valid == 12
        assert m.exact and m.n_splits == math.comb(12, 6) == 924
        assert m.empirical_p_value is not None and 0 < m.empirical_p_value <= 1
        assert sum(m.null_hist_counts) == 924
