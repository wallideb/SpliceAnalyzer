"""
Permutation test for rMATS events
==================================
For each SE event, tests whether the observed ΔΨ is significant relative
to a null distribution built by randomly permuting sample labels.

Algorithm (ΔΨ per event)
-------------------------
1. Collect per-sample PSI values from inc_level_1 and inc_level_2.
2. Pool all n1 + n2 samples.  In each permutation iteration, randomly
   split the pool into groups of size n1 and n2.
3. Compute permuted ΔΨ = mean(perm2) − mean(perm1).
4. Repeat n_iterations times → null distribution for this event.
5. Empirical p-value = fraction of iterations where
       |permuted ΔΨ| >= |observed ΔΨ|.

Algorithm (scalar metric)
--------------------------
• Events are split into G1 (ΔΨ < 0, more skipped in condition 2) and
  G2 (ΔΨ > 0, more included in condition 2) based on PSI values.
• Observed stat = mean(metric_G2) − mean(metric_G1).
• Each permutation shuffles event-to-group assignment and recomputes the
  mean difference.
• Empirical two-tailed p-value as above.

Global null distribution
------------------------
The returned histogram represents the distribution of *all* permuted ΔΨ
values across all events × iterations, which is useful for a combined view.

Performance notes
-----------------
• Uses numpy for vectorized permutation (fast even for large N×K).
• Events without enough valid PSI values are skipped.
• Call from a thread pool (asyncio.to_thread) in the router.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, field
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

    # Null distribution summary (min 5-bucket histogram of permuted ΔΨ)
    null_hist_bins: list[float] = field(default_factory=list)
    null_hist_counts: list[int]  = field(default_factory=list)


@dataclass
class MetricPermResult:
    """Permutation result for a single scalar metric across all events."""
    metric_name: str          # ppt_score | exon_size | frame_in_frame | canonical_sites
    label: str                # human-readable tab label
    observed_stat: float | None = None   # mean(G2) - mean(G1)
    empirical_p_value: float | None = None
    n_valid: int = 0          # events with non-null metric value
    n_g1: int = 0             # events in group ΔΨ<0
    n_g2: int = 0             # events in group ΔΨ>0
    null_hist_bins: list[float] = field(default_factory=list)
    null_hist_counts: list[int]  = field(default_factory=list)


@dataclass
class PermutationResult:
    analysis_id: str
    n_iterations: int
    n_events_tested: int
    events: list[EventPermResult]

    # Global null histogram (all events × all iterations)
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


# ---------------------------------------------------------------------------
# Histogram helper
# ---------------------------------------------------------------------------

def _make_histogram(
    values: Sequence[float],
    n_bins: int = 40,
    lo: float = -1.0,
    hi: float = 1.0,
) -> tuple[list[float], list[int]]:
    """Return (bin_edges[n_bins], counts[n_bins]) for values in [lo, hi]."""
    if not values:
        return [], []
    step = (hi - lo) / n_bins
    counts = [0] * n_bins
    for v in values:
        idx = int((v - lo) / step)
        idx = max(0, min(n_bins - 1, idx))
        counts[idx] += 1
    bins = [round(lo + i * step, 3) for i in range(n_bins)]
    return bins, counts


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
) -> MetricPermResult:
    """Permutation test for a scalar metric split across two event groups.

    Parameters
    ----------
    values_g1    : metric values for events in group 1 (ΔΨ < 0)
    values_g2    : metric values for events in group 2 (ΔΨ > 0)
    """
    n1, n2 = len(values_g1), len(values_g2)
    n_valid = n1 + n2
    if n1 == 0 or n2 == 0 or n_valid < 4:
        return MetricPermResult(
            metric_name=metric_name, label=label,
            n_valid=n_valid, n_g1=n1, n_g2=n2,
        )

    pool = np.array(values_g1 + values_g2, dtype=np.float64)
    observed_stat = float(pool[n1:].mean() - pool[:n1].mean())

    # Vectorized permutation using numpy
    np_rng = np.random.default_rng(rng.randint(0, 2**31))
    indices = np.argsort(np_rng.random((n_iterations, n_valid)), axis=1)
    shuffled = pool[indices]
    null_deltas_arr = shuffled[:, n1:].mean(axis=1) - shuffled[:, :n1].mean(axis=1)
    null_deltas = null_deltas_arr.tolist()

    abs_obs = abs(observed_stat)
    n_extreme = int(np.sum(np.abs(null_deltas_arr) >= abs_obs))
    emp_p = (n_extreme + 1) / (n_iterations + 1)

    hist_bins, hist_counts = _make_histogram(null_deltas, n_bins=30, lo=lo, hi=hi)

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
    )


# ---------------------------------------------------------------------------
# Core permutation engine
# ---------------------------------------------------------------------------

def run_permutation(
    events: list,           # list of SplicingEvent ORM objects
    features: list,         # list of EventSpliceFeature ORM objects (parallel, may contain None)
    n_iterations: int = 500,
    only_se: bool = True,
    seed: int | None = 42,
) -> PermutationResult:
    """Run permutation tests for all events in `events`.

    Parameters
    ----------
    events       : list of SplicingEvent ORM objects with inc_level_1/2 fields.
    features     : parallel list of EventSpliceFeature ORM objects (or None).
    n_iterations : number of permutation iterations per event.
    only_se      : if True, skip non-SE events (which already have ΔΨ).
    seed         : random seed for reproducibility; None = unseeded.
    """
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)

    event_results: list[EventPermResult] = []
    all_null_values: list[float] = []
    all_observed: list[float] = []

    # Per-event observed ΔΨ (for metric group splitting)
    event_deltas: list[tuple[float, object | None]] = []  # (delta_psi, feature)

    for ev, feat in zip(events, features):
        if only_se and ev.event_type != "SE":
            continue

        psi1 = _parse_psi(ev.inc_level_1)
        psi2 = _parse_psi(ev.inc_level_2)

        if not psi1 or not psi2:
            continue

        observed_delta = (_mean(psi2) or 0.0) - (_mean(psi1) or 0.0)
        all_observed.append(observed_delta)
        event_deltas.append((observed_delta, feat))

        n1, n2 = len(psi1), len(psi2)
        pool = np.array(psi1 + psi2, dtype=np.float64)

        # Vectorized permutation: generate all shuffled indices at once
        # Shape: (n_iterations, n1+n2)
        indices = np.argsort(np_rng.random((n_iterations, n1 + n2)), axis=1)
        # Compute mean of group2 - mean of group1 for all iterations at once
        shuffled_all = pool[indices]
        g1_means = shuffled_all[:, :n1].mean(axis=1)
        g2_means = shuffled_all[:, n1:].mean(axis=1)
        null_deltas_arr = g2_means - g1_means

        null_deltas = null_deltas_arr.tolist()
        all_null_values.extend(null_deltas)

        # Empirical two-tailed p-value (vectorized)
        abs_obs = abs(observed_delta)
        n_extreme = int(np.sum(np.abs(null_deltas_arr) >= abs_obs))
        emp_p = (n_extreme + 1) / (n_iterations + 1)   # +1 to avoid p=0

        # Per-event null histogram
        hist_bins, hist_counts = _make_histogram(null_deltas, n_bins=20)

        event_results.append(EventPermResult(
            event_id          = str(ev.id),
            gene_symbol       = ev.gene_symbol,
            observed_delta_psi= round(observed_delta, 4),
            empirical_p_value = round(emp_p, 4),
            n1                = n1,
            n2                = n2,
            null_hist_bins    = hist_bins,
            null_hist_counts  = hist_counts,
        ))

    # Global histograms
    global_bins, global_counts = (
        _make_histogram(all_null_values, n_bins=40)
        if all_null_values else ([], [])
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

    # ── Auxiliary metric permutation tests ──────────────────────────────────
    # Split events by ΔΨ sign: G1 = more skipped (ΔΨ<0), G2 = more included (ΔΨ>0)
    metric_results: list[MetricPermResult] = []
    if event_deltas:
        metric_results = _compute_metric_permutations(event_deltas, n_iterations, rng)

    return PermutationResult(
        analysis_id           = str(events[0].analysis_id) if events else "",
        n_iterations          = n_iterations,
        n_events_tested       = n_tested,
        events                = event_results,
        global_null_hist_bins = global_bins,
        global_null_hist_counts = global_counts,
        observed_hist_bins    = obs_bins,
        observed_hist_counts  = obs_counts,
        pct_p05               = pct_p05,
        pct_p01               = pct_p01,
        metric_results        = metric_results,
    )


def _compute_metric_permutations(
    event_deltas: list[tuple[float, object | None]],
    n_iterations: int,
    rng: random.Random,
) -> list[MetricPermResult]:
    """Build per-metric permutation tests by splitting events on ΔΨ sign."""

    g1_feats = [f for d, f in event_deltas if d < 0 and f is not None]
    g2_feats = [f for d, f in event_deltas if d > 0 and f is not None]

    results: list[MetricPermResult] = []

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
    vals_g1 = _collect(g1_feats, "ppt_score")
    vals_g2 = _collect(g2_feats, "ppt_score")
    results.append(_run_metric_permutation(
        vals_g1, vals_g2, n_iterations, rng,
        metric_name="ppt_score",
        label="PPT Score",
        lo=-1.0, hi=1.0,
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
        norm_g1 = [norm(v) for v in raw_g1]
        norm_g2 = [norm(v) for v in raw_g2]
        results.append(_run_metric_permutation(
            norm_g1, norm_g2, n_iterations, rng,
            metric_name="exon_size",
            label="Exon size",
            lo=-1.0, hi=1.0,
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

    fvals_g1 = [v for f in g1_feats if (v := frame_val(f)) is not None]
    fvals_g2 = [v for f in g2_feats if (v := frame_val(f)) is not None]
    results.append(_run_metric_permutation(
        fvals_g1, fvals_g2, n_iterations, rng,
        metric_name="frame_in_frame",
        label="Phase / In-frame",
        lo=-1.0, hi=1.0,
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

    cvals_g1 = [v for f in g1_feats if (v := canon_val(f)) is not None]
    cvals_g2 = [v for f in g2_feats if (v := canon_val(f)) is not None]
    results.append(_run_metric_permutation(
        cvals_g1, cvals_g2, n_iterations, rng,
        metric_name="canonical_sites",
        label="Sites consensus (GT-AG)",
        lo=-1.0, hi=1.0,
    ))

    return results
