"""
Shared statistical helpers (no scipy dependency)
=================================================
Single implementation of the tests used by the deep-analysis pattern
comparison (``routers/deep_analyses``) and the hnRNP motif enrichment
(``services/hnrnp_motifs``), so that both report identical statistics for
identical inputs:

- :func:`normal_cdf`          Φ(x) = 0.5·erfc(−x/√2) (exact identity)
- :func:`proportion_z_test`   pooled two-proportion z-test
- :func:`mann_whitney_u`      Mann-Whitney U, normal approximation with tie
                              correction and a 0.5 continuity correction
                              (R ``wilcox.test`` / scipy ``use_continuity=True``)
- :func:`bh_adjust`           Benjamini-Hochberg q-values, ``None``-aware

All tests are two-sided and return raw (unrounded) p-values; callers round
for display only, after any multiple-testing correction.
"""

from __future__ import annotations

import math
from typing import Sequence

#: Minimum observations per group for the normal-approximation tests (z / U);
#: below this the approximations are unreliable and the test is not run.
MIN_GROUP_N = 5


def normal_cdf(x: float) -> float:
    """Standard normal CDF via the identity Phi(x) = 0.5 * erfc(-x / sqrt(2)).

    The identity is mathematically exact; the numerical result depends on the
    precision of ``math.erfc`` (the C library), not on a hand-coded
    approximation.
    """
    return 0.5 * math.erfc(-x / math.sqrt(2))


def proportion_z_test(
    k1: int, n1: int, k2: int, n2: int, min_n: int = MIN_GROUP_N,
) -> tuple[float | None, float | None]:
    """Standard pooled two-proportion z-test for H0: p1 = p2.

    Uses the pooled proportion p_pool = (k1+k2)/(n1+n2) to estimate the common
    proportion under H0, giving SE = sqrt(p_pool*(1-p_pool)*(1/n1+1/n2)).
    The two-tailed p-value is 2*(1 - Phi(|z|)).

    This is a large-sample normal approximation, not an exact test; no
    continuity correction is applied.  Returns ``(None, None)`` when either
    group has fewer than *min_n* observations or when the pooled proportion is
    0 or 1 (SE = 0, test undefined).  The caller is responsible for
    multiple-testing correction.
    """
    if n1 < min_n or n2 < min_n:
        return None, None
    p1 = k1 / n1
    p2 = k2 / n2
    p_pool = (k1 + k2) / (n1 + n2)
    if p_pool <= 0 or p_pool >= 1:
        return None, None
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return None, None
    z = (p1 - p2) / se
    p = 2 * (1 - normal_cdf(abs(z)))
    return z, min(1.0, max(0.0, p))


def mann_whitney_u(
    a: Sequence[float], b: Sequence[float], min_n: int = MIN_GROUP_N,
) -> tuple[float | None, float | None]:
    """Two-sided Mann-Whitney U test for H0: the distributions of a and b are equal.

    Returns ``(U_a, p)`` where U_a is the U statistic of sample *a* (number of
    (a_i, b_j) pairs with a_i > b_j, ties counting 1/2).  Values are pooled and
    mid-ranked; the variance of U is corrected for ties,

        σ² = n1·n2/12 · [(N + 1) − Σ(t³ − t) / (N(N − 1))],

    and a 0.5 continuity correction towards the mean is applied before the
    normal approximation, as in R's ``wilcox.test`` and
    ``scipy.stats.mannwhitneyu(use_continuity=True)``.  Rank-based, so it is
    suited to right-skewed variables (exon/intron sizes, motif densities).

    Returns ``(None, None)`` when either sample has fewer than *min_n* values,
    and ``(U_a, None)`` when every pooled value is tied (zero variance: no
    ordering information, the test is undefined and is not counted in a BH
    family).
    """
    n1, n2 = len(a), len(b)
    if n1 < min_n or n2 < min_n:
        return None, None
    n = n1 + n2
    pooled = sorted(
        [(float(v), 0) for v in a] + [(float(v), 1) for v in b],
        key=lambda t: t[0],
    )

    ranks = [0.0] * n
    tie_term = 0.0
    i = 0
    while i < n:
        j = i
        while j + 1 < n and pooled[j + 1][0] == pooled[i][0]:
            j += 1
        t = j - i + 1
        mid_rank = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[k] = mid_rank
        if t > 1:
            tie_term += t ** 3 - t
        i = j + 1

    r1 = sum(rank for rank, (_, grp) in zip(ranks, pooled) if grp == 0)
    u1 = r1 - n1 * (n1 + 1) / 2.0
    mu = n1 * n2 / 2.0
    sigma2 = n1 * n2 / 12.0 * ((n + 1) - tie_term / (n * (n - 1)))
    if sigma2 <= 0.0 or not math.isfinite(sigma2):
        return u1, None
    diff = u1 - mu
    if diff > 0:
        diff -= 0.5
    elif diff < 0:
        diff += 0.5
    z = diff / math.sqrt(sigma2)
    p = 2.0 * (1.0 - normal_cdf(abs(z)))
    return u1, min(1.0, max(0.0, p))


def bh_adjust(p_values: Sequence[float | None]) -> list[float | None]:
    """Benjamini-Hochberg adjusted p-values (q-values), in input order.

    ``None`` entries (tests that could not be run) are ignored when counting
    the family size *m* and are returned as ``None``.
    q_(i) = min_{j ≥ i} ( m · p_(j) / j ), clipped to 1.
    """
    indexed = [(p, i) for i, p in enumerate(p_values) if p is not None]
    out: list[float | None] = [None] * len(p_values)
    m = len(indexed)
    if m == 0:
        return out
    indexed.sort(key=lambda t: t[0])
    running_min = 1.0
    for rank in range(m, 0, -1):
        p, idx = indexed[rank - 1]
        q = min(running_min, p * m / rank)
        running_min = q
        out[idx] = min(1.0, q)
    return out
