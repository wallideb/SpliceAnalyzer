"""
Unit tests for the pure statistical helpers used by the deep-analysis router
(no scipy dependency) and the natural chromosome sort key of the events router.

Run:  cd rmats-viz/backend && python -m pytest tests/test_stats.py -q

Importing the routers pulls FastAPI / SQLAlchemy; the DB engine is created
lazily from the settings defaults, so no database is needed.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

# Allow running from backend/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.routers.deep_analyses import (  # noqa: E402
    _bh_adjust,
    _mann_whitney_u,
    _proportion_z_test,
    _welch_t_test,
)
from app.routers.events import _chr_sort_key  # noqa: E402


# ---------------------------------------------------------------------------
# Welch's t-test
# ---------------------------------------------------------------------------

def test_welch_known_vectors():
    # scipy.stats.ttest_ind([1,2,3,4,5], [2,3,4,5,6], equal_var=False)
    #   → statistic=-1.5811388, pvalue=0.1524976 (df = 8)
    t, p = _welch_t_test([1, 2, 3, 4, 5], [2, 3, 4, 5, 6])
    assert t is not None and p is not None
    assert t == pytest.approx(-1.5811, abs=1e-3)
    assert p == pytest.approx(0.1525, abs=1e-3)


def test_welch_symmetric_and_identical():
    t_ab, p_ab = _welch_t_test([1, 2, 3, 4, 5], [2, 3, 4, 5, 6])
    t_ba, p_ba = _welch_t_test([2, 3, 4, 5, 6], [1, 2, 3, 4, 5])
    assert t_ba == pytest.approx(-t_ab)
    assert p_ba == pytest.approx(p_ab)
    # Identical samples: t = 0, p = 1
    t0, p0 = _welch_t_test([1, 2, 3, 4], [1, 2, 3, 4])
    assert t0 == pytest.approx(0.0)
    assert p0 == pytest.approx(1.0)


def test_welch_guards():
    assert _welch_t_test([1.0], [1.0, 2.0]) == (None, None)
    assert _welch_t_test([], []) == (None, None)
    # Zero variance in both groups → undefined SE → None
    assert _welch_t_test([2, 2, 2], [3, 3, 3]) == (None, None)


# ---------------------------------------------------------------------------
# Mann-Whitney U
# ---------------------------------------------------------------------------

def test_mann_whitney_no_overlap_extreme():
    # scipy.stats.mannwhitneyu(a, b, alternative='two-sided', use_continuity=True)
    #   a=[1..5], b=[6..10] → U1 = 0, p = 0.011820...
    u, p = _mann_whitney_u([1, 2, 3, 4, 5], [6, 7, 8, 9, 10])
    assert u == pytest.approx(0.0)
    assert p == pytest.approx(0.01182, abs=1e-3)


def test_mann_whitney_with_ties():
    # scipy.stats.mannwhitneyu([1,2,2,3,4,5], [3,4,4,5,6,7], alternative='two-sided')
    #   → U1 = 5.5, p ≈ 0.0503 (tie-corrected normal approx. w/ continuity)
    u, p = _mann_whitney_u([1, 2, 2, 3, 4, 5], [3, 4, 4, 5, 6, 7])
    assert u == pytest.approx(5.5)
    assert p == pytest.approx(0.0503, abs=2e-3)


def test_mann_whitney_symmetry_and_identity():
    a = [10, 12, 15, 18, 20, 22]
    b = [11, 13, 14, 16, 17, 30]
    u_ab, p_ab = _mann_whitney_u(a, b)
    u_ba, p_ba = _mann_whitney_u(b, a)
    assert u_ab + u_ba == pytest.approx(len(a) * len(b))
    assert p_ab == pytest.approx(p_ba)
    # Same distribution → U = n1*n2/2 and p = 1
    u_eq, p_eq = _mann_whitney_u([1, 2, 3, 4, 5], [1, 2, 3, 4, 5])
    assert u_eq == pytest.approx(12.5)
    assert p_eq == pytest.approx(1.0)


def test_mann_whitney_guards():
    # fewer than 5 per group → not tested
    assert _mann_whitney_u([1, 2, 3, 4], [1, 2, 3, 4, 5]) == (None, None)
    # all values tied → no ordering information → p None
    u, p = _mann_whitney_u([3, 3, 3, 3, 3], [3, 3, 3, 3, 3])
    assert u == pytest.approx(12.5)
    assert p is None


# ---------------------------------------------------------------------------
# Two-proportion z-test
# ---------------------------------------------------------------------------

def test_proportion_z_known_values():
    # 50/100 vs 30/100: p_pool = 0.4, SE = sqrt(0.4*0.6*0.02) = 0.069282
    #   z = 0.2 / 0.069282 = 2.8868, p = 2*(1-Phi(2.8868)) = 0.00389
    z, p = _proportion_z_test(50, 100, 30, 100)
    assert z == pytest.approx(2.887, abs=1e-3)
    assert p == pytest.approx(0.0039, abs=1e-3)


def test_proportion_z_guards():
    # n < 5 in either group → None
    assert _proportion_z_test(2, 4, 30, 100) == (None, None)
    assert _proportion_z_test(30, 100, 1, 3) == (None, None)
    assert _proportion_z_test(0, 0, 0, 0) == (None, None)
    # p_pool = 0 or 1 → SE = 0 → undefined
    assert _proportion_z_test(0, 10, 0, 10) == (None, None)
    assert _proportion_z_test(10, 10, 10, 10) == (None, None)
    # boundary: exactly 5 per group is allowed
    z, p = _proportion_z_test(5, 5, 0, 5)
    assert z is not None and p is not None


# ---------------------------------------------------------------------------
# Benjamini-Hochberg
# ---------------------------------------------------------------------------

def test_bh_adjust_known_values():
    # R: p.adjust(c(0.01, 0.04, 0.03, 0.005), method="BH") → 0.02 0.04 0.04 0.02
    q = _bh_adjust([0.01, 0.04, 0.03, 0.005])
    assert q == pytest.approx([0.02, 0.04, 0.04, 0.02])


def test_bh_adjust_monotone_and_clipped():
    q = _bh_adjust([0.5, 0.9, 0.2])
    # m=3: sorted 0.2→0.6, 0.5→0.75, 0.9→0.9 ; step-down min keeps 0.6, 0.75, 0.9
    assert q == pytest.approx([0.75, 0.9, 0.6])
    assert all(0.0 <= v <= 1.0 for v in q)
    assert _bh_adjust([1.0, 1.0]) == pytest.approx([1.0, 1.0])


def test_bh_adjust_handles_none():
    q = _bh_adjust([None, 0.01, None, 0.02])
    assert q[0] is None and q[2] is None
    # only two evaluable tests: m = 2 → 0.02, 0.02
    assert q[1] == pytest.approx(0.02)
    assert q[3] == pytest.approx(0.02)
    assert _bh_adjust([]) == []
    assert _bh_adjust([None]) == [None]


# ---------------------------------------------------------------------------
# Natural chromosome ordering
# ---------------------------------------------------------------------------

def test_chr_sort_key_mapping():
    assert _chr_sort_key("chr1") == (1, "")
    assert _chr_sort_key("chr22") == (22, "")
    assert _chr_sort_key("chrX") == (23, "")
    assert _chr_sort_key("chrY") == (24, "")
    assert _chr_sort_key("chrM") == (25, "")
    assert _chr_sort_key("chrMT") == (25, "")
    assert _chr_sort_key("MT") == (25, "")
    assert _chr_sort_key("7") == (7, "")
    assert _chr_sort_key("CHRx") == (23, "")
    # other contigs sort after canonical chromosomes, alphabetically
    assert _chr_sort_key("chr1_KI270706v1_random")[0] == 100
    assert _chr_sort_key("chrUn_GL000220v1") == (100, "UN_GL000220V1")
    assert _chr_sort_key(None) == (100, "")


def test_chr_sort_key_natural_order():
    chroms = ["chr10", "chr2", "chrX", "chr1", "chrM", "chr22", "chrY", "chr11", "chrUn_x", "chr1_random"]
    ordered = sorted(chroms, key=_chr_sort_key)
    assert ordered[:7] == ["chr1", "chr2", "chr10", "chr11", "chr22", "chrX", "chrY"]
    assert ordered[7] == "chrM"
    assert set(ordered[8:]) == {"chrUn_x", "chr1_random"}
    assert ordered[8:] == sorted(ordered[8:], key=lambda c: c[3:].upper())


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
