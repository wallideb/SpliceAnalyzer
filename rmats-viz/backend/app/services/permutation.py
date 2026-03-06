"""
Permutation test for rMATS events
==================================
For each SE event, tests whether the observed ΔΨ is significant relative
to a null distribution built by randomly permuting sample labels.

Algorithm (per event)
---------------------
1. Collect per-sample PSI values from inc_level_1 and inc_level_2.
2. Pool all n1 + n2 samples.  In each permutation iteration, randomly
   split the pool into groups of size n1 and n2.
3. Compute permuted ΔΨ = mean(perm2) − mean(perm1).
4. Repeat n_iterations times → null distribution for this event.
5. Empirical p-value = fraction of iterations where
       |permuted ΔΨ| >= |observed ΔΨ|.

Global null distribution
------------------------
The returned histogram represents the distribution of *all* permuted ΔΨ
values across all events × iterations, which is useful for a combined view.

Performance notes
-----------------
• Pure Python / statistics module — no numpy required.
• Events without enough valid PSI values are skipped.
• For large analyses (N events, K iterations) this can be slow.
  Call from a thread pool (asyncio.to_thread) in the router.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, field
from typing import Sequence


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
    step = (hi - lo) / n_bins
    counts = [0] * n_bins
    for v in values:
        idx = int((v - lo) / step)
        idx = max(0, min(n_bins - 1, idx))
        counts[idx] += 1
    bins = [round(lo + i * step, 3) for i in range(n_bins)]
    return bins, counts


# ---------------------------------------------------------------------------
# Core permutation engine
# ---------------------------------------------------------------------------

def run_permutation(
    events: list,          # list of SplicingEvent ORM objects
    n_iterations: int = 500,
    only_se: bool = True,
    seed: int | None = 42,
) -> PermutationResult:
    """Run permutation tests for all events in `events`.

    Parameters
    ----------
    events       : list of SplicingEvent ORM objects with inc_level_1/2 fields.
    n_iterations : number of permutation iterations per event.
    only_se      : if True, skip non-SE events (which already have ΔΨ).
    seed         : random seed for reproducibility; None = unseeded.
    """
    rng = random.Random(seed)

    event_results: list[EventPermResult] = []
    all_null_values: list[float] = []
    all_observed: list[float] = []

    for ev in events:
        if only_se and ev.event_type != "SE":
            continue

        psi1 = _parse_psi(ev.inc_level_1)
        psi2 = _parse_psi(ev.inc_level_2)

        if not psi1 or not psi2:
            continue

        observed_delta = (_mean(psi2) or 0.0) - (_mean(psi1) or 0.0)
        all_observed.append(observed_delta)

        n1, n2 = len(psi1), len(psi2)
        pool = psi1 + psi2

        null_deltas: list[float] = []
        for _ in range(n_iterations):
            shuffled = pool[:]
            rng.shuffle(shuffled)
            g1, g2 = shuffled[:n1], shuffled[n1:]
            perm_delta = statistics.mean(g2) - statistics.mean(g1)
            null_deltas.append(perm_delta)
            all_null_values.append(perm_delta)

        # Empirical two-tailed p-value
        abs_obs = abs(observed_delta)
        n_extreme = sum(1 for d in null_deltas if abs(d) >= abs_obs)
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
        round(sum(1 for r in event_results if (r.empirical_p_value or 1) < 0.05) / n_tested * 100, 1)
        if n_tested else None
    )
    pct_p01 = (
        round(sum(1 for r in event_results if (r.empirical_p_value or 1) < 0.01) / n_tested * 100, 1)
        if n_tested else None
    )

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
    )
