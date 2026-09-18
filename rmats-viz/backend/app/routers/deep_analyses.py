"""
Deep-analysis CRUD router.

POST   /analyses/{id}/deep-analyses           — create (tags events by threshold)
GET    /analyses/{id}/deep-analyses           — list saved deep analyses
GET    /deep-analyses/{id}                    — get detail
DELETE /deep-analyses/{id}                    — delete
GET    /deep-analyses/{id}/events             — list events (filterable by significance)
GET    /deep-analyses/{id}/pattern-comparison — dual-group pattern stats
"""

from __future__ import annotations

import asyncio
import logging
import math
import statistics
import uuid
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.analysis import Analysis
from app.models.event import SplicingEvent
from app.models.deep_analysis import DeepAnalysis, DeepAnalysisEvent
from app.models.splice import EventSpliceFeature
from app.schemas.deep_analysis import (
    DeepAnalysisCreate,
    DeepAnalysisEventsPage,
    DeepAnalysisListItem,
    DeepAnalysisResponse,
)
from app.schemas.event import SplicingEventResponse
from app.services.splice_features import compute_pwm, iupac_consensus, ppt_t_content, ppt_c_content

logger = logging.getLogger(__name__)

router = APIRouter(tags=["deep-analyses"])

_DAE_BATCH = 5_000  # junction rows per pg_insert (stays within PG param limit)


# ---------------------------------------------------------------------------
# POST /analyses/{analysis_id}/deep-analyses
# ---------------------------------------------------------------------------

@router.post(
    "/analyses/{analysis_id}/deep-analyses",
    response_model=DeepAnalysisResponse,
    status_code=201,
)
async def create_deep_analysis(
    analysis_id: uuid.UUID,
    body: DeepAnalysisCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a deep analysis: tag every event as significant/non-significant."""
    analysis = (
        await db.execute(select(Analysis).where(Analysis.id == analysis_id))
    ).scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "Analysis not found")

    # Auto-name: CandidateGene-FDR-PSI-pvalue(if set)-Date
    if body.name:
        name = body.name
    else:
        gene_part = ""
        if analysis.mutated_genes:
            symbols = [g.get("symbol", "") for g in analysis.mutated_genes if g.get("symbol")]
            gene_part = "_".join(symbols[:3]) + "-" if symbols else ""
        pval_part = f"-p{body.pvalue_threshold}" if body.pvalue_threshold is not None else ""
        from datetime import date as _d
        name = f"{gene_part}FDR{body.fdr_threshold}-PSI{body.delta_psi_min}{pval_part}-{_d.today().isoformat()}"

    # Fetch all events for this analysis
    q = select(
        SplicingEvent.id, SplicingEvent.fdr, SplicingEvent.p_value, SplicingEvent.inc_level_difference,
    ).where(SplicingEvent.analysis_id == analysis_id)
    rows = (await db.execute(q)).all()

    # Tag each event: FDR ≤ threshold AND |ΔΨ| ≥ minimum AND (when a p-value
    # maximum is set) p ≤ pvalue_threshold.
    n_sig = 0
    n_not_sig = 0
    event_records: list[dict] = []

    for event_id, fdr, p_value, inc_level_diff in rows:
        fdr_ok = fdr is not None and fdr <= body.fdr_threshold
        dpsi_ok = (
            inc_level_diff is not None
            and abs(inc_level_diff) >= body.delta_psi_min
        )
        pv_ok = body.pvalue_threshold is None or (
            p_value is not None and p_value <= body.pvalue_threshold
        )
        is_sig = fdr_ok and dpsi_ok and pv_ok
        if is_sig:
            n_sig += 1
        else:
            n_not_sig += 1
        event_records.append({"event_id": event_id, "is_significant": is_sig})

    deep = DeepAnalysis(
        analysis_id=analysis_id,
        name=name,
        fdr_threshold=body.fdr_threshold,
        pvalue_threshold=body.pvalue_threshold,
        delta_psi_min=body.delta_psi_min,
        modules=body.modules,
        n_significant=n_sig,
        n_not_significant=n_not_sig,
        permutation_iterations=body.permutation_iterations,
        status="ready",
    )
    db.add(deep)
    await db.flush()  # materialise deep.id before bulk insert

    # Bulk-insert junction rows in batches to stay within pg param limit
    for i in range(0, len(event_records), _DAE_BATCH):
        batch = event_records[i : i + _DAE_BATCH]
        for rec in batch:
            rec["deep_analysis_id"] = deep.id
        await db.execute(pg_insert(DeepAnalysisEvent).values(batch))

    await db.commit()
    await db.refresh(deep)
    return deep


# ---------------------------------------------------------------------------
# GET /analyses/{analysis_id}/deep-analyses
# ---------------------------------------------------------------------------

@router.get(
    "/analyses/{analysis_id}/deep-analyses",
    response_model=list[DeepAnalysisListItem],
)
async def list_deep_analyses(
    analysis_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """List all saved deep analyses for an analysis, newest first."""
    q = (
        select(DeepAnalysis)
        .where(DeepAnalysis.analysis_id == analysis_id)
        .order_by(DeepAnalysis.created_at.desc())
    )
    rows = (await db.execute(q)).scalars().all()
    return rows


# ---------------------------------------------------------------------------
# GET /deep-analyses/{deep_analysis_id}
# ---------------------------------------------------------------------------

@router.get(
    "/deep-analyses/{deep_analysis_id}",
    response_model=DeepAnalysisResponse,
)
async def get_deep_analysis(
    deep_analysis_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    deep = (
        await db.execute(
            select(DeepAnalysis).where(DeepAnalysis.id == deep_analysis_id)
        )
    ).scalar_one_or_none()
    if not deep:
        raise HTTPException(404, "Deep analysis not found")
    return deep


# ---------------------------------------------------------------------------
# DELETE /deep-analyses/{deep_analysis_id}
# ---------------------------------------------------------------------------

@router.delete("/deep-analyses/{deep_analysis_id}", status_code=204)
async def delete_deep_analysis(
    deep_analysis_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    deep = (
        await db.execute(
            select(DeepAnalysis).where(DeepAnalysis.id == deep_analysis_id)
        )
    ).scalar_one_or_none()
    if not deep:
        raise HTTPException(404, "Deep analysis not found")
    await db.delete(deep)
    await db.commit()


# ---------------------------------------------------------------------------
# GET /deep-analyses/{deep_analysis_id}/events
# ---------------------------------------------------------------------------

@router.get(
    "/deep-analyses/{deep_analysis_id}/events",
    response_model=DeepAnalysisEventsPage,
)
async def list_deep_analysis_events(
    deep_analysis_id: uuid.UUID,
    significant: bool | None = Query(None, description="Filter by significance"),
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Return a page of events associated with this deep analysis
    (ordered by FDR ascending), optionally filtered by significance.

    Response: ``{items, total, page, page_size, pages}`` (same shape as
    ``GET /analyses/{id}/events``).
    """
    deep = (
        await db.execute(
            select(DeepAnalysis).where(DeepAnalysis.id == deep_analysis_id)
        )
    ).scalar_one_or_none()
    if not deep:
        raise HTTPException(404, "Deep analysis not found")

    q = (
        select(SplicingEvent)
        .join(DeepAnalysisEvent, DeepAnalysisEvent.event_id == SplicingEvent.id)
        .where(DeepAnalysisEvent.deep_analysis_id == deep_analysis_id)
    )
    if significant is not None:
        q = q.where(DeepAnalysisEvent.is_significant == significant)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()

    q = (
        q.order_by(SplicingEvent.fdr.asc().nulls_last(), SplicingEvent.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(q)).scalars().all()
    pages = max(1, -(-total // page_size))  # ceiling division
    return DeepAnalysisEventsPage(
        items=[SplicingEventResponse.model_validate(r) for r in rows],
        total=total, page=page, page_size=page_size, pages=pages,
    )


# ---------------------------------------------------------------------------
# Pattern comparison schemas
# ---------------------------------------------------------------------------

class GroupPatternStats(BaseModel):
    n_events: int = 0
    n_se_with_features: int = 0
    exon_size_mean: float | None = None
    exon_size_median: float | None = None
    pct_canonical_gt: float | None = None
    pct_canonical_ag: float | None = None
    ppt_mean_score: float | None = None
    ppt_mean_t_content: float | None = None
    ppt_mean_c_content: float | None = None
    frame_in_frame: int = 0
    frame_frameshift: int = 0
    frame_non_coding: int = 0
    bp_found_pct: float | None = None
    donor_pwm: list[dict[str, float]] | None = None
    acceptor_pwm: list[dict[str, float]] | None = None
    donor_consensus: str | None = None
    acceptor_consensus: str | None = None
    # Flanking exon splice sites
    pct_upstream_gt: float | None = None
    pct_downstream_ag: float | None = None
    upstream_donor_pwm: list[dict[str, float]] | None = None
    downstream_acceptor_pwm: list[dict[str, float]] | None = None
    upstream_donor_consensus: str | None = None
    downstream_acceptor_consensus: str | None = None
    mean_delta_psi: float | None = None
    # Flanking intron sizes
    upstream_intron_size_mean: float | None = None
    upstream_intron_size_median: float | None = None
    downstream_intron_size_mean: float | None = None
    downstream_intron_size_median: float | None = None


class StatTestResult(BaseModel):
    feature: str
    test_name: str
    statistic: float | None = None
    p_value: float | None = None
    # Benjamini-Hochberg adjusted p-value across every test of the panel
    # (None when the test could not be run).
    q_value: float | None = None
    significant: bool = False       # raw p < 0.05
    significant_fdr: bool = False   # BH q < 0.05


class PatternComparisonResponse(BaseModel):
    significant: GroupPatternStats
    not_significant: GroupPatternStats
    statistical_tests: list[StatTestResult] = []


# ---------------------------------------------------------------------------
# GET /deep-analyses/{deep_analysis_id}/pattern-comparison
# ---------------------------------------------------------------------------

@router.get(
    "/deep-analyses/{deep_analysis_id}/pattern-comparison",
    response_model=PatternComparisonResponse,
)
async def get_pattern_comparison(
    deep_analysis_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Compute pattern statistics separately for significant and non-significant groups."""
    deep = (
        await db.execute(
            select(DeepAnalysis).where(DeepAnalysis.id == deep_analysis_id)
        )
    ).scalar_one_or_none()
    if not deep:
        raise HTTPException(404, "Deep analysis not found")

    # Fetch all SE events with their features and significance tagging
    q = (
        select(SplicingEvent, EventSpliceFeature, DeepAnalysisEvent.is_significant)
        .join(DeepAnalysisEvent, DeepAnalysisEvent.event_id == SplicingEvent.id)
        .outerjoin(EventSpliceFeature, EventSpliceFeature.event_id == SplicingEvent.id)
        .where(
            DeepAnalysisEvent.deep_analysis_id == deep_analysis_id,
            SplicingEvent.event_type == "SE",
        )
    )
    rows = (await db.execute(q)).all()

    # Separate into two groups
    sig_feats: list[EventSpliceFeature] = []
    sig_events: list[SplicingEvent] = []
    nonsig_feats: list[EventSpliceFeature] = []
    nonsig_events: list[SplicingEvent] = []

    for ev, feat, is_sig in rows:
        if is_sig:
            sig_events.append(ev)
            if feat is not None:
                sig_feats.append(feat)
        else:
            nonsig_events.append(ev)
            if feat is not None:
                nonsig_feats.append(feat)

    return PatternComparisonResponse(
        significant=_compute_group_stats(sig_events, sig_feats),
        not_significant=_compute_group_stats(nonsig_events, nonsig_feats),
        statistical_tests=_compute_stat_tests(sig_events, sig_feats, nonsig_events, nonsig_feats),
    )


# ---------------------------------------------------------------------------
# Statistical test helpers (no scipy dependency)
# ---------------------------------------------------------------------------

def _welch_t_test(vals1: list[float], vals2: list[float]) -> tuple[float | None, float | None]:
    """Welch's t-test for unequal variances. Returns (t_stat, p_value) or (None, None).

    Caveat: the test assumes approximately normal sampling distributions.
    Exon/intron sizes are typically right-skewed; p-values may be inaccurate
    for small or heavily skewed groups (n < 30).
    """
    n1, n2 = len(vals1), len(vals2)
    if n1 < 2 or n2 < 2:
        return None, None
    m1, m2 = statistics.mean(vals1), statistics.mean(vals2)
    v1 = statistics.variance(vals1)
    v2 = statistics.variance(vals2)
    se2 = v1 / n1 + v2 / n2
    if se2 <= 0.0 or not math.isfinite(se2):
        return None, None
    # Welch-Satterthwaite degrees of freedom
    denom = (v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1)
    if denom <= 0.0 or not math.isfinite(denom):
        return None, None
    df = se2 ** 2 / denom
    if not math.isfinite(df) or df <= 0.0:
        return None, None
    t_stat = (m1 - m2) / math.sqrt(se2)
    # Two-tailed p-value: 2 * P(T ≥ |t|)
    try:
        p = min(1.0, 2.0 * _t_upper_tail(abs(t_stat), df))
    except ArithmeticError:
        # Regularized beta continued fraction did not converge —
        # return t-stat without a p-value rather than crashing.
        return t_stat, None
    return t_stat, p


def _t_upper_tail(t: float, df: float) -> float:
    """Return the upper-tail probability P(T ≥ t) for Student's t-distribution.

    Uses the numerically evaluated regularized incomplete beta function:
      P(T ≥ t) = 0.5 * I_{df/(df+t²)}(df/2, 1/2)

    For a two-tailed test: p = min(1.0, 2.0 * _t_upper_tail(abs(t_stat), df))
    """
    x = df / (df + t * t)
    a, b = df / 2.0, 0.5
    return 0.5 * _regularized_beta(x, a, b)


def _regularized_beta(x: float, a: float, b: float, max_iter: int = 200) -> float:
    """Regularized incomplete beta function I_x(a,b) via Lentz's continued fraction.

    Boundary cases are exact by definition: I_0(a,b) = 0 and I_1(a,b) = 1.
    In the t-tail context, x=1 arises only when t=0; _t_upper_tail then returns
    0.5 * 1 = 0.5, giving a two-tailed p-value of 1.0, which is correct.

    The symmetry relation I_x(a,b) = 1 - I_{1-x}(b,a) is applied when x is large
    (x > (a+1)/(a+b+2)) to keep x in the convergence region of the continued
    fraction and avoid numerical breakdown for x close to 1.
    """
    if x <= 0:
        return 0.0
    if x >= 1:          # I_1(a,b) = 1 by definition
        return 1.0
    # Use symmetry for numerical stability when x is large
    if x > (a + 1.0) / (a + b + 2.0):
        return 1.0 - _regularized_beta(1.0 - x, b, a, max_iter)
    # Use the log-beta prefix
    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(a * math.log(x) + b * math.log1p(-x) - lbeta) / a

    # Modified Lentz's algorithm for continued fraction
    f = 1.0
    c = 1.0
    d = 1.0 - (a + b) * x / (a + 1)
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    f = d
    for m in range(1, max_iter + 1):
        # Even step
        num = m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m))
        d = 1.0 + num * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + num / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        f *= c * d
        # Odd step
        num = -((a + m) * (a + b + m) * x) / ((a + 2 * m) * (a + 2 * m + 1))
        d = 1.0 + num * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + num / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = c * d
        f *= delta
        if abs(delta - 1.0) < 3e-7:
            return front * f
    raise ArithmeticError("Incomplete beta continued fraction did not converge")


def _proportion_z_test(k1: int, n1: int, k2: int, n2: int) -> tuple[float | None, float | None]:
    """Standard pooled two-proportion z-test for H0: p1 = p2.

    Uses the pooled proportion p_pool = (k1+k2)/(n1+n2) to estimate the common
    proportion under H0, giving SE = sqrt(p_pool*(1-p_pool)*(1/n1+1/n2)).
    The two-tailed p-value is 2*(1 - Phi(|z|)).

    This is a large-sample normal approximation, not an exact test.  For small
    expected counts Fisher's exact test is generally preferred.  No continuity
    correction is applied.  Groups with fewer than 5 observations are not
    tested (None, None).  SE = 0 (and None is returned) whenever p_pool is 0
    or 1, i.e. all observations across both groups are failures or all are
    successes; the test is undefined in that case.
    """
    if n1 < _MIN_GROUP_N or n2 < _MIN_GROUP_N:
        return None, None
    p1 = k1 / n1
    p2 = k2 / n2
    p_pool = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2)) if 0 < p_pool < 1 else 0
    if se == 0:
        return None, None
    z = (p1 - p2) / se
    # Two-tailed p-value from normal distribution
    p = 2 * (1 - _normal_cdf(abs(z)))
    return round(z, 4), round(p, 4)


def _normal_cdf(x: float) -> float:
    """Standard normal CDF via the identity Phi(x) = 0.5 * erfc(-x / sqrt(2)).

    The identity is mathematically exact; the numerical result depends on the
    precision of math.erfc (Python's C-library implementation), not on any
    hand-coded Abramowitz-Stegun approximation.
    """
    return 0.5 * math.erfc(-x / math.sqrt(2))


def _mann_whitney_u(a: list[float], b: list[float]) -> tuple[float | None, float | None]:
    """Two-sided Mann-Whitney U test (normal approximation with tie correction).

    Returns (U, p) where U is the statistic of sample *a* (U1), or (None, None)
    when a group has fewer than ``_MIN_GROUP_N`` values or every value is tied.

    Ranks are mid-ranks; the variance of U is corrected for ties:
        σ² = n1·n2/12 · [(N + 1) − Σ(t³ − t) / (N(N − 1))]
    A continuity correction of 0.5 is applied, as in R's wilcox.test and
    scipy.stats.mannwhitneyu(use_continuity=True).  Rank-based, so it is
    suited to right-skewed variables (exon/intron sizes, PPT scores).
    """
    n1, n2 = len(a), len(b)
    if n1 < _MIN_GROUP_N or n2 < _MIN_GROUP_N:
        return None, None
    n = n1 + n2
    pooled = sorted(((float(v), 0) for v in a), key=lambda t: t[0])
    pooled = sorted(pooled + [(float(v), 1) for v in b], key=lambda t: t[0])

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
        return u1, None  # all values tied → no ordering information
    diff = u1 - mu
    # Continuity correction toward the mean
    if diff > 0:
        diff -= 0.5
    elif diff < 0:
        diff += 0.5
    z = diff / math.sqrt(sigma2)
    p = min(1.0, 2.0 * (1.0 - _normal_cdf(abs(z))))
    return u1, p


def _bh_adjust(p_values: list[float | None]) -> list[float | None]:
    """Benjamini-Hochberg adjusted p-values (q-values).

    ``None`` entries (tests that could not be run) are ignored for m and
    returned as ``None``.  q_(i) = min_{j ≥ i} ( m · p_(j) / j ), clipped to 1.
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


_MIN_GROUP_N = 5  # minimum observations per group for the z / U tests


def _compute_stat_tests(
    sig_events: list,
    sig_feats: list,
    nonsig_events: list,
    nonsig_feats: list,
) -> list[StatTestResult]:
    """Compute statistical tests comparing significant vs non-significant groups.

    Continuous features (mean ΔΨ, exon size, PPT score / T / C content,
    intron sizes) are tested twice: Welch's t-test (``feature``) and the
    rank-based Mann-Whitney U test (``feature + "_mwu"``), the latter being
    robust to the right-skew of size distributions.  Proportions use the
    pooled two-proportion z-test (≥ 5 observations per group).  Benjamini-
    Hochberg q-values are computed across the whole panel; ``significant``
    remains the raw p < 0.05 call and ``significant_fdr`` is q < 0.05.
    The number of tests is ``len(result)`` — never hard-code it.
    """
    results: list[StatTestResult] = []

    def _add(feature: str, test_name: str, stat, p) -> None:
        results.append(StatTestResult(
            feature=feature, test_name=test_name, statistic=stat, p_value=p,
            significant=(p if p is not None else 1) < 0.05,
        ))

    def _continuous(feature: str, vals_sig: list[float], vals_ns: list[float]) -> None:
        t_stat, p_val = _welch_t_test(vals_sig, vals_ns)
        _add(feature, "Welch's t-test", t_stat, p_val)
        u_stat, p_u = _mann_whitney_u(vals_sig, vals_ns)
        _add(f"{feature}_mwu", "mann_whitney_u", u_stat, p_u)

    # 1. Mean ΔΨ
    _continuous(
        "mean_delta_psi",
        [ev.inc_level_difference for ev in sig_events if ev.inc_level_difference is not None],
        [ev.inc_level_difference for ev in nonsig_events if ev.inc_level_difference is not None],
    )

    # 2. Exon size
    _continuous(
        "exon_size",
        [f.exon_size for f in sig_feats if f.exon_size is not None],
        [f.exon_size for f in nonsig_feats if f.exon_size is not None],
    )

    # 3. PPT score
    _continuous(
        "ppt_score",
        [f.ppt_score for f in sig_feats if f.ppt_score is not None and f.donor_seq],
        [f.ppt_score for f in nonsig_feats if f.ppt_score is not None and f.donor_seq],
    )

    # 3b. PPT T content
    _continuous(
        "ppt_t_content",
        [ppt_t_content(f.ppt_seq) for f in sig_feats if f.ppt_seq],
        [ppt_t_content(f.ppt_seq) for f in nonsig_feats if f.ppt_seq],
    )

    # 3c. PPT C content
    _continuous(
        "ppt_c_content",
        [ppt_c_content(f.ppt_seq) for f in sig_feats if f.ppt_seq],
        [ppt_c_content(f.ppt_seq) for f in nonsig_feats if f.ppt_seq],
    )

    # Canonical-site flags can be None (window truncated at a contig end):
    # unknown → excluded from numerator AND denominator of the z-tests.
    def _prop(feats: list, flag_attr: str, seq_attr: str, min_len: int) -> tuple[int, int]:
        known = [
            getattr(f, flag_attr) for f in feats
            if getattr(f, seq_attr) and len(getattr(f, seq_attr)) >= min_len
            and getattr(f, flag_attr) is not None
        ]
        return sum(1 for v in known if v), len(known)

    # 4. Canonical GT (5'SS) — proportion z-test
    sig_with_seq = [f for f in sig_feats if f.donor_seq and len(f.donor_seq) >= 9]
    ns_with_seq = [f for f in nonsig_feats if f.donor_seq and len(f.donor_seq) >= 9]
    k1, n1 = _prop(sig_feats, "donor_is_gt", "donor_seq", 9)
    k2, n2 = _prop(nonsig_feats, "donor_is_gt", "donor_seq", 9)
    _add("canonical_gt", "Proportion z-test", *_proportion_z_test(k1, n1, k2, n2))

    # 5. Canonical AG (3'SS) — proportion z-test
    k1, n1 = _prop(sig_feats, "acceptor_is_ag", "acceptor_seq", 23)
    k2, n2 = _prop(nonsig_feats, "acceptor_is_ag", "acceptor_seq", 23)
    _add("canonical_ag", "Proportion z-test", *_proportion_z_test(k1, n1, k2, n2))

    # 6. In-frame proportion (known frames only) — proportion z-test
    sig_frame = [f for f in sig_feats if f.frame_class and f.frame_class != "unknown"]
    ns_frame = [f for f in nonsig_feats if f.frame_class and f.frame_class != "unknown"]
    k1 = sum(1 for f in sig_frame if f.frame_class == "in_frame")
    k2 = sum(1 for f in ns_frame if f.frame_class == "in_frame")
    _add("in_frame_pct", "Proportion z-test", *_proportion_z_test(k1, len(sig_frame), k2, len(ns_frame)))

    # 7. Branch point found — proportion z-test
    k1 = sum(1 for f in sig_with_seq if f.bp_motif_found)
    k2 = sum(1 for f in ns_with_seq if f.bp_motif_found)
    _add("bp_found", "Proportion z-test", *_proportion_z_test(k1, len(sig_with_seq), k2, len(ns_with_seq)))

    # 8. Upstream donor GT (flanking exon) — proportion z-test
    k1, n1 = _prop(sig_feats, "upstream_donor_is_gt", "upstream_donor_seq", 9)
    k2, n2 = _prop(nonsig_feats, "upstream_donor_is_gt", "upstream_donor_seq", 9)
    _add("upstream_canonical_gt", "Proportion z-test", *_proportion_z_test(k1, n1, k2, n2))

    # 9. Downstream acceptor AG (flanking exon) — proportion z-test
    k1, n1 = _prop(sig_feats, "downstream_acceptor_is_ag", "downstream_acceptor_seq", 23)
    k2, n2 = _prop(nonsig_feats, "downstream_acceptor_is_ag", "downstream_acceptor_seq", 23)
    _add("downstream_canonical_ag", "Proportion z-test", *_proportion_z_test(k1, n1, k2, n2))

    # 10. Upstream intron size
    _continuous(
        "upstream_intron_size",
        [f.upstream_intron_size for f in sig_feats if f.upstream_intron_size is not None],
        [f.upstream_intron_size for f in nonsig_feats if f.upstream_intron_size is not None],
    )

    # 11. Downstream intron size
    _continuous(
        "downstream_intron_size",
        [f.downstream_intron_size for f in sig_feats if f.downstream_intron_size is not None],
        [f.downstream_intron_size for f in nonsig_feats if f.downstream_intron_size is not None],
    )

    # Benjamini-Hochberg across the whole panel
    q_values = _bh_adjust([r.p_value for r in results])
    for r, q in zip(results, q_values):
        r.q_value = round(q, 6) if q is not None else None
        r.significant_fdr = q is not None and q < 0.05

    return results


def _compute_group_stats(
    events: list[SplicingEvent],
    feats: list[EventSpliceFeature],
) -> GroupPatternStats:
    """Compute pattern statistics for a group of events."""
    feats_with_seq = [f for f in feats if f.donor_seq]

    # Exon sizes
    sizes = [f.exon_size for f in feats if f.exon_size is not None]

    # Canonical-site flags may be None (truncated window near a contig end):
    # such events are unknown and excluded from BOTH numerator and denominator.
    # Donor
    donor_9 = [f.donor_seq[:9] for f in feats_with_seq if f.donor_seq and len(f.donor_seq) >= 9]
    gt_known = [f.donor_is_gt for f in feats_with_seq if f.donor_seq and len(f.donor_seq) >= 9 and f.donor_is_gt is not None]
    n_gt = sum(1 for v in gt_known if v)

    # Acceptor
    acc_23 = [f.acceptor_seq[-23:] for f in feats_with_seq if f.acceptor_seq and len(f.acceptor_seq) >= 23]
    ag_known = [f.acceptor_is_ag for f in feats_with_seq if f.acceptor_seq and len(f.acceptor_seq) >= 23 and f.acceptor_is_ag is not None]
    n_ag = sum(1 for v in ag_known if v)

    # Upstream donor (flanking exon)
    up_donor_9 = [f.upstream_donor_seq[:9] for f in feats_with_seq if f.upstream_donor_seq and len(f.upstream_donor_seq) >= 9]
    up_gt_known = [f.upstream_donor_is_gt for f in feats_with_seq if f.upstream_donor_seq and len(f.upstream_donor_seq) >= 9 and f.upstream_donor_is_gt is not None]
    n_up_gt = sum(1 for v in up_gt_known if v)

    # Downstream acceptor (flanking exon)
    dn_acc_23 = [f.downstream_acceptor_seq[-23:] for f in feats_with_seq if f.downstream_acceptor_seq and len(f.downstream_acceptor_seq) >= 23]
    dn_ag_known = [f.downstream_acceptor_is_ag for f in feats_with_seq if f.downstream_acceptor_seq and len(f.downstream_acceptor_seq) >= 23 and f.downstream_acceptor_is_ag is not None]
    n_dn_ag = sum(1 for v in dn_ag_known if v)

    # PPT
    ppt_scores = [f.ppt_score for f in feats_with_seq if f.ppt_score is not None]
    ppt_t_vals = [ppt_t_content(f.ppt_seq) for f in feats_with_seq if f.ppt_seq]
    ppt_c_vals = [ppt_c_content(f.ppt_seq) for f in feats_with_seq if f.ppt_seq]

    # Frame
    fc = Counter(f.frame_class or "unknown" for f in feats)

    # Branch point
    bp_total = len(feats_with_seq)
    bp_found = sum(1 for f in feats_with_seq if f.bp_motif_found)

    # Mean ΔΨ
    dpsi = [ev.inc_level_difference for ev in events if ev.inc_level_difference is not None]

    # Intron sizes
    up_introns = [f.upstream_intron_size for f in feats if f.upstream_intron_size is not None]
    dn_introns = [f.downstream_intron_size for f in feats if f.downstream_intron_size is not None]

    return GroupPatternStats(
        n_events=len(events),
        n_se_with_features=len(feats),
        exon_size_mean=round(statistics.mean(sizes), 1) if sizes else None,
        exon_size_median=round(statistics.median(sizes), 1) if sizes else None,
        pct_canonical_gt=round(n_gt / len(gt_known) * 100, 1) if gt_known else None,
        pct_canonical_ag=round(n_ag / len(ag_known) * 100, 1) if ag_known else None,
        ppt_mean_score=round(statistics.mean(ppt_scores), 3) if ppt_scores else None,
        ppt_mean_t_content=round(statistics.mean(ppt_t_vals), 3) if ppt_t_vals else None,
        ppt_mean_c_content=round(statistics.mean(ppt_c_vals), 3) if ppt_c_vals else None,
        frame_in_frame=fc.get("in_frame", 0),
        frame_frameshift=fc.get("frameshift", 0),
        frame_non_coding=fc.get("non_coding", 0),
        bp_found_pct=round(bp_found / bp_total * 100, 1) if bp_total else None,
        donor_pwm=compute_pwm(donor_9) if donor_9 else None,
        acceptor_pwm=compute_pwm(acc_23) if acc_23 else None,
        donor_consensus=iupac_consensus(donor_9) if donor_9 else None,
        acceptor_consensus=iupac_consensus(acc_23) if acc_23 else None,
        pct_upstream_gt=round(n_up_gt / len(up_gt_known) * 100, 1) if up_gt_known else None,
        pct_downstream_ag=round(n_dn_ag / len(dn_ag_known) * 100, 1) if dn_ag_known else None,
        upstream_donor_pwm=compute_pwm(up_donor_9) if up_donor_9 else None,
        downstream_acceptor_pwm=compute_pwm(dn_acc_23) if dn_acc_23 else None,
        upstream_donor_consensus=iupac_consensus(up_donor_9) if up_donor_9 else None,
        downstream_acceptor_consensus=iupac_consensus(dn_acc_23) if dn_acc_23 else None,
        mean_delta_psi=round(statistics.mean(dpsi), 3) if dpsi else None,
        upstream_intron_size_mean=round(statistics.mean(up_introns), 1) if up_introns else None,
        upstream_intron_size_median=round(statistics.median(up_introns), 1) if up_introns else None,
        downstream_intron_size_mean=round(statistics.mean(dn_introns), 1) if dn_introns else None,
        downstream_intron_size_median=round(statistics.median(dn_introns), 1) if dn_introns else None,
    )


# ===========================================================================
# hnRNP motif enrichment analysis
# ===========================================================================

class MotifEnrichmentItem(BaseModel):
    motif_name: str
    protein: str
    region: str
    sig_hit_count: int
    sig_total: int
    bg_hit_count: int
    bg_total: int
    sig_density: float
    bg_density: float
    # Presence test (fraction of events with ≥ 1 hit): two-proportion z-test, BH
    z_stat: float | None = None
    p_value: float | None = None
    p_adjusted: float | None = None
    significant: bool = False
    # Density test (per-event motif density): Mann-Whitney U, BH
    density_u_stat: float | None = None
    density_p_value: float | None = None
    density_p_adjusted: float | None = None
    density_significant: bool = False
    regulatory_effect: str | None = None  # ESE/ESS/ISE/ISS or null


class HnRNPMotifResponse(BaseModel):
    n_sig_events: int
    n_bg_events: int
    # Region names in scanning order (7 regions, see hnrnp_motifs.REGION_NAMES)
    regions: list[str] = []
    results: list[MotifEnrichmentItem]


@router.get(
    "/deep-analyses/{deep_analysis_id}/hnrnp-motifs",
    response_model=HnRNPMotifResponse,
)
async def get_hnrnp_motifs(
    deep_analysis_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Run hnRNP motif enrichment: compare motif frequency in significant
    vs non-significant SE events (rMAPS2-inspired analysis)."""
    from app.services import hnrnp_motifs as hm
    from app.services.hnrnp_motifs import (
        REGION_NAMES, SERegions, define_se_regions, compare_groups, scan_group,
        REGULATORY_EFFECTS,
    )
    from app.services.sequence import extract_regions_batch, reverse_complement
    from app.config import settings

    _FIVE_SS_EXCL = getattr(hm, "_FIVE_SS_EXCL", 6)
    _THREE_SS_EXCL = getattr(hm, "_THREE_SS_EXCL", 20)
    n_regions = len(REGION_NAMES)

    deep = (
        await db.execute(
            select(DeepAnalysis).where(DeepAnalysis.id == deep_analysis_id)
        )
    ).scalar_one_or_none()
    if not deep:
        raise HTTPException(404, "Deep analysis not found")

    # Fetch all SE events with significance tagging
    q = (
        select(
            SplicingEvent,
            DeepAnalysisEvent.is_significant,
        )
        .join(DeepAnalysisEvent, DeepAnalysisEvent.event_id == SplicingEvent.id)
        .where(
            DeepAnalysisEvent.deep_analysis_id == deep_analysis_id,
            SplicingEvent.event_type == "SE",
        )
    )
    rows = (await db.execute(q)).all()

    sig_events: list[SplicingEvent] = []
    bg_events: list[SplicingEvent] = []
    for ev, is_sig in rows:
        (sig_events if is_sig else bg_events).append(ev)

    def _build_regions(events: list[SplicingEvent], label: str = "") -> list[SERegions]:
        """Extract the genomic regions (``REGION_NAMES`` order) per event and
        fetch sequences in one batch."""
        if not events:
            return []
        all_bed_regions: list[tuple[str, int, int]] = []
        strands: list[str] = []

        n_missing_coords = 0
        n_null_up_ee = 0   # + strand: upstream_ee missing
        n_null_up_es = 0   # - strand: upstream_es missing
        n_null_dn_es = 0   # + strand: downstream_es missing
        n_null_dn_ee = 0   # - strand: downstream_ee missing
        n_short_up_intron = 0
        n_short_dn_intron = 0

        for ev in events:
            strand = ev.strand or "+"
            if not ev.chr or ev.exon_start is None or ev.exon_end is None:
                n_missing_coords += 1
                for _ in range(n_regions):
                    all_bed_regions.append(("", 0, 0))
                strands.append(strand)
                continue

            # Diagnose why intron regions might be empty for this event
            if strand == "+":
                if ev.upstream_ee is None:
                    n_null_up_ee += 1
                else:
                    up_intron = ev.exon_start - ev.upstream_ee
                    if up_intron <= _FIVE_SS_EXCL + _THREE_SS_EXCL:
                        n_short_up_intron += 1
                if ev.downstream_es is None:
                    n_null_dn_es += 1
                else:
                    dn_intron = ev.downstream_es - ev.exon_end
                    if dn_intron <= _FIVE_SS_EXCL + _THREE_SS_EXCL:
                        n_short_dn_intron += 1
            else:
                # Minus strand: rMATS "downstream" exon (higher coords) is 5′ flanking.
                # Upstream intron spans [exon_end, downstream_es); downstream intron spans [upstream_ee, exon_start).
                if ev.downstream_es is None:
                    n_null_up_es += 1
                else:
                    up_intron = ev.downstream_es - ev.exon_end
                    if up_intron <= _FIVE_SS_EXCL + _THREE_SS_EXCL:
                        n_short_up_intron += 1
                if ev.upstream_ee is None:
                    n_null_dn_ee += 1
                else:
                    dn_intron = ev.exon_start - ev.upstream_ee
                    if dn_intron <= _FIVE_SS_EXCL + _THREE_SS_EXCL:
                        n_short_dn_intron += 1

            bed = define_se_regions(
                ev.chr, strand,
                ev.exon_start, ev.exon_end,
                ev.upstream_es, ev.upstream_ee,
                ev.downstream_es, ev.downstream_ee,
            )
            if len(bed) != n_regions:
                raise RuntimeError(
                    f"define_se_regions returned {len(bed)} regions, expected {n_regions}"
                )
            all_bed_regions.extend(bed)
            strands.append(strand)

        n = len(events)
        tag = f"[{label}] " if label else ""
        if n_missing_coords:
            logger.warning("%shnRNP: %d/%d events skipped — missing chr/exon_start/exon_end", tag, n_missing_coords, n)
        if n_null_up_ee or n_null_up_es:
            logger.warning("%shnRNP: %d/%d events — null upstream flanking coord (upstream_ee/es) → no upstream intron",
                           tag, n_null_up_ee + n_null_up_es, n)
        if n_null_dn_es or n_null_dn_ee:
            logger.warning("%shnRNP: %d/%d events — null downstream flanking coord (downstream_es/ee) → no downstream intron",
                           tag, n_null_dn_es + n_null_dn_ee, n)
        if n_short_up_intron:
            logger.warning("%shnRNP: %d/%d events — upstream intron ≤ %d nt (exclusion zones consume it) → no upstream intron",
                           tag, n_short_up_intron, n, _FIVE_SS_EXCL + _THREE_SS_EXCL)
        if n_short_dn_intron:
            logger.warning("%shnRNP: %d/%d events — downstream intron ≤ %d nt → no downstream intron",
                           tag, n_short_dn_intron, n, _FIVE_SS_EXCL + _THREE_SS_EXCL)
        logger.info("%shnRNP region extraction: %d events total", tag, n)

        seqs = extract_regions_batch(all_bed_regions, settings.GRCH38_FASTA)

        results: list[SERegions] = []
        for idx, strand in enumerate(strands):
            s = seqs[idx * n_regions : idx * n_regions + n_regions]
            if strand == "-":
                s = [reverse_complement(x) if x else "" for x in s]
            results.append(SERegions(**dict(zip(REGION_NAMES, s))))
        return results

    # Extract regions for both groups concurrently (two independent samtools calls)
    sig_regions, bg_regions = await asyncio.gather(
        asyncio.to_thread(_build_regions, sig_events, "sig"),
        asyncio.to_thread(_build_regions, bg_events, "bg"),
    )

    # Scan both groups concurrently; compare_groups is fast (pure Python)
    sig_scan, bg_scan = await asyncio.gather(
        asyncio.to_thread(scan_group, sig_regions),
        asyncio.to_thread(scan_group, bg_regions),
    )
    enrichment = await asyncio.to_thread(compare_groups, sig_scan, bg_scan)

    return HnRNPMotifResponse(
        n_sig_events=len(sig_events),
        n_bg_events=len(bg_events),
        regions=list(REGION_NAMES),
        results=[
            MotifEnrichmentItem(
                motif_name=r.motif_name,
                protein=r.protein,
                region=r.region,
                sig_hit_count=r.sig_hit_count,
                sig_total=r.sig_total,
                bg_hit_count=r.bg_hit_count,
                bg_total=r.bg_total,
                sig_density=r.sig_density,
                bg_density=r.bg_density,
                z_stat=r.z_stat,
                p_value=r.p_value,
                p_adjusted=r.p_adjusted,
                significant=r.significant,
                density_u_stat=getattr(r, "density_u_stat", None),
                density_p_value=getattr(r, "density_p_value", None),
                density_p_adjusted=getattr(r, "density_p_adjusted", None),
                density_significant=bool(getattr(r, "density_significant", False)),
                regulatory_effect=REGULATORY_EFFECTS.get(r.protein, {}).get(r.region),
            )
            for r in enrichment
        ],
    )


# ===========================================================================
# Enrichr gene-set enrichment analysis
# ===========================================================================

class EnrichrTermItem(BaseModel):
    library: str
    rank: int
    term: str
    p_value: float
    adjusted_p_value: float
    z_score: float
    combined_score: float
    overlap: str
    genes: list[str]


class EnrichrResponse(BaseModel):
    n_genes_submitted: int
    terms: list[EnrichrTermItem]
    error: str | None = None


@router.get(
    "/deep-analyses/{deep_analysis_id}/enrichr",
    response_model=EnrichrResponse,
)
async def get_enrichr_enrichment(
    deep_analysis_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Run Enrichr pathway enrichment on gene symbols from significant events."""
    from app.services.enrichr import run_enrichment

    deep = (
        await db.execute(
            select(DeepAnalysis).where(DeepAnalysis.id == deep_analysis_id)
        )
    ).scalar_one_or_none()
    if not deep:
        raise HTTPException(404, "Deep analysis not found")

    # Get unique gene symbols from significant SE events
    q = (
        select(SplicingEvent.gene_symbol)
        .join(DeepAnalysisEvent, DeepAnalysisEvent.event_id == SplicingEvent.id)
        .where(
            DeepAnalysisEvent.deep_analysis_id == deep_analysis_id,
            DeepAnalysisEvent.is_significant.is_(True),
            SplicingEvent.gene_symbol.isnot(None),
        )
        .distinct()
    )
    rows = (await db.execute(q)).scalars().all()
    gene_symbols = [s for s in rows if s and s.strip()]

    if not gene_symbols:
        return EnrichrResponse(
            n_genes_submitted=0,
            terms=[],
            error="No gene symbols found in significant events",
        )

    result = await asyncio.to_thread(run_enrichment, gene_symbols)
    return EnrichrResponse(
        n_genes_submitted=result.n_genes_submitted,
        terms=[
            EnrichrTermItem(
                library=t.library,
                rank=t.rank,
                term=t.term,
                p_value=t.p_value,
                adjusted_p_value=t.adjusted_p_value,
                z_score=t.z_score,
                combined_score=t.combined_score,
                overlap=t.overlap,
                genes=t.genes,
            )
            for t in result.terms
        ],
        error=result.error,
    )
