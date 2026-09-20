"""
Permutation test for rMATS events
==================================
For each SE event, tests whether the observed ΔΨ is significant relative
to a null distribution built by permuting sample labels.

Sign convention
---------------
ΔΨ = mean(PSI_sample1) − mean(PSI_sample2), consistent with rMATS
IncLevelDifference = IncLevel1 − IncLevel2.

Observed ΔΨ (displayed vs tested)
---------------------------------
The *displayed* ``observed_delta_psi`` is rMATS' ``IncLevelDifference`` when
available (it is the value shown everywhere else in the application);
otherwise mean(PSI_1) − mean(PSI_2) recomputed from the parsed replicates.
The *test statistic* is always the value recomputed from the same replicate
values that feed the null distribution, so the observed label assignment
is exactly one of the enumerated/permuted assignments (rMATS rounds
IncLevelDifference to 3 dp, which would otherwise break the "observed split
is included" argument of the exact test).  Events where either group has no
valid PSI value are skipped.

Algorithm (ΔΨ per event)
-------------------------
1. Collect per-sample PSI values from inc_level_1 and inc_level_2
   (n1 and n2 replicates; NA values are dropped).
2. Pool all n1 + n2 samples.  There are C(n1 + n2, n1) distinct ways of
   splitting the pool into groups of size n1 and n2.
3. Exact enumeration — when C(n1 + n2, n1) <= ``exact_max_splits`` (default
   5000, e.g. any design with up to 7 vs 7 replicates), *all* distinct label
   splits are enumerated (itertools.combinations) and the null distribution
   is the complete set of permuted ΔΨ = mean(split1) − mean(split2).  The
   two-tailed p-value is
       p = #{splits : |permuted ΔΨ| ≥ |observed ΔΨ|} / n_splits
   No +1 correction is needed: the observed assignment is one of the
   enumerated splits, so the numerator is at least 1 and p ≥ 1/n_splits.
   With 2 vs 2 replicates there are only 6 splits (minimum p = 1/6 ≈ 0.167),
   with 3 vs 3 there are 20 (minimum p = 0.05): the resolution of the test is
   limited by the design, not by the number of iterations, and the result
   reports this through ``exact``, ``n_splits`` and ``min_p_attainable``.
4. Monte-Carlo — otherwise, ``n_iterations`` random splits are drawn
   (numpy, vectorised) and the empirical two-tailed p-value uses the
   Phipson & Smyth (2010) correction
       p = (#{|permuted ΔΨ| ≥ |observed ΔΨ|} + 1) / (n_iterations + 1)
   The +1 prevents impossible zero p-values with random (non-exhaustive)
   permutations; the minimum attainable p is 1/(n_iterations + 1).

Algorithm (scalar metric, auxiliary)
--------------------------------------
Events are split by the sign of their per-event ΔΨ into two groups (G1: ΔΨ < 0,
G2: ΔΨ > 0).  A scalar metric is extracted from the associated splice-feature
record of each event (where available); the observed statistic is
mean(G2) − mean(G1).  The same exact-enumeration / Monte-Carlo rule as above is
applied to the event-to-group labels.  The grouping variable is derived from
the data (ΔΨ sign), not an external experimental label; results should be
interpreted as exploratory.  The specific metrics tested are implementation
details derived from the `features` list passed to `run_permutation` — they
are not explicit parameters of the function interface.

Min-max normalization
---------------------
For metrics that are normalised before permutation (e.g. exon size), the
global min and max are computed once from the full pooled dataset before
any permutation step.  This is a single fixed monotone linear transform
applied uniformly to all values, which preserves the ordering of |Δ| and
therefore leaves the two-sided permutation p-value unchanged (apart from
floating-point rounding).  If normalisation were recomputed within each
permutation or separately per group, the test statistic would change and
the p-value would not be preserved.

Global null distribution
------------------------
The returned histogram represents the distribution of *all* permuted ΔΨ
values across all events (exact splits or Monte-Carlo iterations), which is
useful for a combined view.  It is accumulated as 40 fixed-edge bin counts on
[−1, 1] while events are processed; the individual null values are never
kept (120 k events × 500 iterations would be 60 M floats).

Reproducibility
---------------
A fixed seed (default 42) makes results reproducible across runs that use
the same code path.  Pass seed=None for an unseeded (non-reproducible) run.
The exact path is deterministic regardless of the seed.

Performance notes
-----------------
• Uses numpy for vectorised permutation (fast even for large N×K); the
  enumerated split masks are cached per (n1, n2) design.
• Events without enough valid PSI values are skipped.
• Call from a thread pool (asyncio.to_thread) in the router.

References
----------
- Phipson B & Smyth GK. Permutation p-values should never be zero.
  Stat Appl Genet Mol Biol 2010; 9:Article39
"""

from __future__ import annotations

import math
import random
import statistics
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import combinations
from typing import Sequence

import numpy as np


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_psi(s: str | None) -> list[float]:
    """Parse a comma-separated PSI string into a list of valid floats."""
    if not s:
        return []
    vals: list[float] = []
    for tok in s.split(","):
        tok = tok.strip()
        try:
            v = float(tok)
            if math.isfinite(v) and 0.0 <= v <= 1.0:
                vals.append(v)
        except ValueError:
            pass
    return vals


def _mean(vals: list[float]) -> float | None:
    return statistics.mean(vals) if vals else None


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class EventPermResult:
    event_id: str
    gene_symbol: str | None
    observed_delta_psi: float | None
    empirical_p_value: float | None
    n1: int
    n2: int

    # Null distribution summary (20-bin histogram of permuted ΔΨ)
    null_hist_bins: list[float] = field(default_factory=list)
    null_hist_counts: list[int]  = field(default_factory=list)

    # True when every distinct label split was enumerated; n_splits is then
    # the number of splits (p ≥ 1/n_splits).  False → Monte-Carlo, n_splits None.
    exact: bool = False
    n_splits: int | None = None


@dataclass
class MetricPermResult:
    """Permutation result for a single scalar metric across all events."""
    metric_name: str          # identifier for the metric (implementation-defined)
    label: str                # human-readable tab label
    observed_stat: float | None = None   # mean(G2) - mean(G1)
    empirical_p_value: float | None = None
    n_valid: int = 0          # events with non-null metric value
    n_g1: int = 0             # events in group ΔΨ<0
    n_g2: int = 0             # events in group ΔΨ>0
    null_hist_bins: list[float] = field(default_factory=list)
    null_hist_counts: list[int]  = field(default_factory=list)
    exact: bool = False
    n_splits: int | None = None


@dataclass
class PermutationResult:
    analysis_id: str
    n_iterations: int
    n_events_tested: int
    events: list[EventPermResult]

    # Global null histogram (all events × all splits/iterations)
    global_null_hist_bins: list[float]   = field(default_factory=list)
    global_null_hist_counts: list[int]   = field(default_factory=list)

    # Observed ΔΨ histogram (for overlay)
    observed_hist_bins: list[float]  = field(default_factory=list)
    observed_hist_counts: list[int]  = field(default_factory=list)

    # Fraction of events with empirical p < 0.05 / 0.01
    pct_p05: float | None = None
    pct_p01: float | None = None

    # Auxiliary metric results
    metric_results: list[MetricPermResult] = field(default_factory=list)

    # Design summary
    exact_fraction: float = 0.0            # fraction of tested events on the exact path
    min_p_attainable: float | None = None  # smallest p the most common design can produce
    n_replicates_g1: int | None = None     # mode of n1 over tested events
    n_replicates_g2: int | None = None     # mode of n2 over tested events


# ---------------------------------------------------------------------------
# Histogram helpers
# ---------------------------------------------------------------------------

def _hist_edges(n_bins: int, lo: float, hi: float) -> list[float]:
    step = (hi - lo) / n_bins
    return [round(lo + i * step, 3) for i in range(n_bins)]


def _hist_counts(values: np.ndarray, n_bins: int, lo: float, hi: float) -> np.ndarray:
    """Fixed-edge bin counts for *values*; out-of-range values go to the edge bins."""
    step = (hi - lo) / n_bins
    idx = np.floor((values - lo) / step).astype(np.int64)
    np.clip(idx, 0, n_bins - 1, out=idx)
    return np.bincount(idx, minlength=n_bins)


def _make_histogram(
    values: Sequence[float],
    n_bins: int = 40,
    lo: float = -1.0,
    hi: float = 1.0,
) -> tuple[list[float], list[int]]:
    """Return (bin_edges[n_bins], counts[n_bins]) for values in [lo, hi].

    Same binning as :func:`_hist_counts` (used for the accumulated global null).
    """
    if len(values) == 0:
        return [], []
    counts = _hist_counts(np.asarray(values, dtype=np.float64), n_bins, lo, hi)
    return _hist_edges(n_bins, lo, hi), counts.tolist()


# ---------------------------------------------------------------------------
# Null distribution engine (exact enumeration or Monte-Carlo)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=64)
def _split_masks(n1: int, n2: int) -> np.ndarray:
    """Boolean matrix (n_splits, n1+n2): row r is True on the members of group 1
    in the r-th distinct label split.  Row 0 is the observed assignment
    (the first n1 positions), because itertools.combinations is lexicographic.
    """
    n = n1 + n2
    combs = np.fromiter(
        (i for c in combinations(range(n), n1) for i in c),
        dtype=np.int64,
    ).reshape(-1, n1)
    masks = np.zeros((combs.shape[0], n), dtype=bool)
    masks[np.arange(combs.shape[0])[:, None], combs] = True
    return masks


def _null_deltas(
    pool: np.ndarray,
    n1: int,
    n_iterations: int,
    np_rng: np.random.Generator,
    exact_max_splits: int,
) -> tuple[np.ndarray, float, float, bool, int | None]:
    """Null distribution of mean(group1) − mean(group2) for a pooled sample.

    ``pool`` holds the n1 group-1 values followed by the n2 group-2 values.
    Returns (null_deltas, observed_delta, p_value, exact, n_splits).
    """
    n = pool.shape[0]
    n2 = n - n1
    if math.comb(n, n1) <= exact_max_splits:
        masks = _split_masks(n1, n2)
        g1_means = (pool * masks).sum(axis=1) / n1
        g2_means = (pool * ~masks).sum(axis=1) / n2
        null = g1_means - g2_means
        observed = float(null[0])          # row 0 is the observed labelling
        n_splits = int(null.shape[0])
        p = float(np.count_nonzero(np.abs(null) >= abs(observed))) / n_splits
        return null, observed, p, True, n_splits

    observed = float(pool[:n1].mean() - pool[n1:].mean())
    # Vectorised random splits: argsort of uniform noise = random permutation per row
    indices = np.argsort(np_rng.random((n_iterations, n)), axis=1)
    shuffled = pool[indices]
    null = shuffled[:, :n1].mean(axis=1) - shuffled[:, n1:].mean(axis=1)
    n_extreme = int(np.count_nonzero(np.abs(null) >= abs(observed)))
    p = (n_extreme + 1) / (n_iterations + 1)   # Phipson–Smyth: never zero
    return null, observed, p, False, None


# ---------------------------------------------------------------------------
# Generic scalar metric permutation
# ---------------------------------------------------------------------------

def _run_metric_permutation(
    values_g1: list[float],
    values_g2: list[float],
    n_iterations: int,
    rng: random.Random,
    metric_name: str,
    label: str,
    lo: float = -1.0,
    hi: float = 1.0,
    exact_max_splits: int = 5000,
) -> MetricPermResult:
    """Permutation test for a scalar metric split across two event groups.

    Parameters
    ----------
    values_g1    : metric values for events in group 1 (ΔΨ < 0)
    values_g2    : metric values for events in group 2 (ΔΨ > 0)

    The statistic is mean(G2) − mean(G1); the engine computes
    mean(first block) − mean(second block), so G2 is passed as the first block.
    """
    n1, n2 = len(values_g1), len(values_g2)
    n_valid = n1 + n2
    if n1 == 0 or n2 == 0 or n_valid < 4:
        return MetricPermResult(
            metric_name=metric_name, label=label,
            n_valid=n_valid, n_g1=n1, n_g2=n2,
        )

    pool = np.array(values_g2 + values_g1, dtype=np.float64)
    np_rng = np.random.default_rng(rng.randint(0, 2**31))
    null, observed_stat, emp_p, exact, n_splits = _null_deltas(
        pool, n2, n_iterations, np_rng, exact_max_splits,
    )

    hist_bins, hist_counts = _make_histogram(null, n_bins=30, lo=lo, hi=hi)

    return MetricPermResult(
        metric_name=metric_name,
        label=label,
        observed_stat=round(observed_stat, 4),
        empirical_p_value=round(emp_p, 4),
        n_valid=n_valid,
        n_g1=n1,
        n_g2=n2,
        null_hist_bins=hist_bins,
        null_hist_counts=hist_counts,
        exact=exact,
        n_splits=n_splits,
    )


# ---------------------------------------------------------------------------
# Core permutation engine
# ---------------------------------------------------------------------------

_GLOBAL_BINS = 40


def run_permutation(
    events: list,           # list of SplicingEvent ORM objects
    features: list,         # list of EventSpliceFeature ORM objects (parallel, may contain None)
    n_iterations: int = 500,
    only_se: bool = True,
    seed: int | None = 42,
    exact_max_splits: int = 5000,
) -> PermutationResult:
    """Run permutation tests for all events in `events`.

    Parameters
    ----------
    events           : list of SplicingEvent ORM objects with inc_level_1/2 fields.
    features         : parallel list of EventSpliceFeature ORM objects (or None).
    n_iterations     : number of Monte-Carlo iterations per event (used only
                       when the design has more than `exact_max_splits` splits).
    only_se          : if True, skip non-SE events (which already have ΔΨ).
    seed             : random seed for reproducibility; None = unseeded.
    exact_max_splits : enumerate all C(n1+n2, n1) label splits when their
                       number is at most this value; otherwise Monte-Carlo.
    """
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)

    event_results: list[EventPermResult] = []
    global_counts = np.zeros(_GLOBAL_BINS, dtype=np.int64)
    n_global = 0
    all_observed: list[float] = []

    # Per-event observed ΔΨ (for metric group splitting)
    event_deltas: list[tuple[float, object | None]] = []  # (delta_psi, feature)
    designs: Counter[tuple[int, int]] = Counter()
    n_exact = 0

    for ev, feat in zip(events, features):
        if only_se and ev.event_type != "SE":
            continue

        psi1 = _parse_psi(ev.inc_level_1)
        psi2 = _parse_psi(ev.inc_level_2)
        mean1, mean2 = _mean(psi1), _mean(psi2)
        if mean1 is None or mean2 is None:
            continue

        n1, n2 = len(psi1), len(psi2)
        pool = np.array(psi1 + psi2, dtype=np.float64)
        null, tested_delta, emp_p, exact, n_splits = _null_deltas(
            pool, n1, n_iterations, np_rng, exact_max_splits,
        )

        # Displayed ΔΨ: rMATS IncLevelDifference when present, else recomputed.
        inc_diff = getattr(ev, "inc_level_difference", None)
        observed_delta = float(inc_diff) if inc_diff is not None else (mean1 - mean2)
        all_observed.append(observed_delta)
        event_deltas.append((observed_delta, feat))

        # Accumulate the global null as fixed-edge bin counts (no value kept)
        global_counts += _hist_counts(null, _GLOBAL_BINS, -1.0, 1.0)
        n_global += null.shape[0]

        # Per-event null histogram
        hist_bins, hist_counts = _make_histogram(null, n_bins=20)

        designs[(n1, n2)] += 1
        if exact:
            n_exact += 1

        event_results.append(EventPermResult(
            event_id          = str(ev.id),
            gene_symbol       = ev.gene_symbol,
            observed_delta_psi= round(observed_delta, 4),
            empirical_p_value = round(emp_p, 4),
            n1                = n1,
            n2                = n2,
            null_hist_bins    = hist_bins,
            null_hist_counts  = hist_counts,
            exact             = exact,
            n_splits          = n_splits,
        ))

    # Global histograms
    global_bins, global_counts_list = (
        (_hist_edges(_GLOBAL_BINS, -1.0, 1.0), global_counts.tolist())
        if n_global else ([], [])
    )
    obs_bins, obs_counts = (
        _make_histogram(all_observed, n_bins=40)
        if all_observed else ([], [])
    )

    n_tested = len(event_results)
    pct_p05 = (
        round(sum(1 for r in event_results if r.empirical_p_value is not None and r.empirical_p_value < 0.05) / n_tested * 100, 1)
        if n_tested else None
    )
    pct_p01 = (
        round(sum(1 for r in event_results if r.empirical_p_value is not None and r.empirical_p_value < 0.01) / n_tested * 100, 1)
        if n_tested else None
    )

    # Design summary: most common (n1, n2) and the smallest p it can produce
    exact_fraction = n_exact / n_tested if n_tested else 0.0
    n_rep_g1: int | None = None
    n_rep_g2: int | None = None
    min_p: float | None = None
    if designs:
        (n_rep_g1, n_rep_g2), _ = designs.most_common(1)[0]
        n_splits_mode = math.comb(n_rep_g1 + n_rep_g2, n_rep_g1)
        min_p = (
            1.0 / n_splits_mode if n_splits_mode <= exact_max_splits
            else 1.0 / (n_iterations + 1)
        )

    # ── Auxiliary metric permutation tests ──────────────────────────────────
    metric_results: list[MetricPermResult] = []
    if event_deltas:
        metric_results = _compute_metric_permutations(
            event_deltas, n_iterations, rng, exact_max_splits,
        )

    return PermutationResult(
        analysis_id           = str(events[0].analysis_id) if events else "",
        n_iterations          = n_iterations,
        n_events_tested       = n_tested,
        events                = event_results,
        global_null_hist_bins = global_bins,
        global_null_hist_counts = global_counts_list,
        observed_hist_bins    = obs_bins,
        observed_hist_counts  = obs_counts,
        pct_p05               = pct_p05,
        pct_p01               = pct_p01,
        metric_results        = metric_results,
        exact_fraction        = round(exact_fraction, 4),
        min_p_attainable      = min_p,
        n_replicates_g1       = n_rep_g1,
        n_replicates_g2       = n_rep_g2,
    )


def _compute_metric_permutations(
    event_deltas: list[tuple[float, object | None]],
    n_iterations: int,
    rng: random.Random,
    exact_max_splits: int = 5000,
) -> list[MetricPermResult]:
    """Build per-metric permutation tests by splitting events on ΔΨ sign (G1: ΔΨ<0, G2: ΔΨ>0)."""
    g1_feats = [f for d, f in event_deltas if d < 0 and f is not None]
    g2_feats = [f for d, f in event_deltas if d > 0 and f is not None]

    results: list[MetricPermResult] = []

    def _run(vals_g1: list[float], vals_g2: list[float], name: str, label: str) -> MetricPermResult:
        return _run_metric_permutation(
            vals_g1, vals_g2, n_iterations, rng,
            metric_name=name, label=label, lo=-1.0, hi=1.0,
            exact_max_splits=exact_max_splits,
        )

    # Helper: extract scalar from feature, return None if absent/invalid
    def _get(feat, attr: str) -> float | None:
        v = getattr(feat, attr, None)
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    def _collect(feats: list, attr: str, transform=None) -> list[float]:
        out = []
        for f in feats:
            v = _get(f, attr)
            if v is not None:
                out.append(transform(v) if transform else v)
        return out

    # ── 1. PPT score ─────────────────────────────────────────────────────────
    results.append(_run(
        _collect(g1_feats, "ppt_score"), _collect(g2_feats, "ppt_score"),
        "ppt_score", "PPT Score",
    ))

    # ── 2. Exon size (normalised to [0, 1] range for histogram) ─────────────
    # Collect raw sizes, then normalise
    raw_g1 = _collect(g1_feats, "exon_size")
    raw_g2 = _collect(g2_feats, "exon_size")
    all_sizes = raw_g1 + raw_g2
    if all_sizes:
        size_min = min(all_sizes)
        size_max = max(all_sizes)
        size_range = max(size_max - size_min, 1)
        norm = lambda v: (v - size_min) / size_range
        results.append(_run(
            [norm(v) for v in raw_g1], [norm(v) for v in raw_g2],
            "exon_size", "Exon size",
        ))
    else:
        results.append(MetricPermResult(
            metric_name="exon_size", label="Exon size",
            n_valid=0, n_g1=len(g1_feats), n_g2=len(g2_feats),
        ))

    # ── 3. Frame: fraction in_frame (0.0 or 1.0 per event) ──────────────────
    def frame_val(f) -> float | None:
        fc = getattr(f, "frame_class", None)
        if fc is None or fc == "unknown":
            return None
        return 1.0 if fc == "in_frame" else 0.0

    results.append(_run(
        [v for f in g1_feats if (v := frame_val(f)) is not None],
        [v for f in g2_feats if (v := frame_val(f)) is not None],
        "frame_in_frame", "Phase / In-frame",
    ))

    # ── 4. Canonical sites (donor_is_gt + acceptor_is_ag → score 0,0.5,1) ───
    def canon_val(f) -> float | None:
        d = getattr(f, "donor_is_gt", None)
        a = getattr(f, "acceptor_is_ag", None)
        if d is None and a is None:
            return None
        score = 0.0
        n = 0
        if d is not None:
            score += 1.0 if d else 0.0
            n += 1
        if a is not None:
            score += 1.0 if a else 0.0
            n += 1
        return score / n

    results.append(_run(
        [v for f in g1_feats if (v := canon_val(f)) is not None],
        [v for f in g2_feats if (v := canon_val(f)) is not None],
        "canonical_sites", "Sites consensus (GT-AG)",
    ))

    return results
