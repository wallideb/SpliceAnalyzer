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

import math
import statistics
import uuid
from collections import Counter
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.analysis import Analysis
from app.models.event import SplicingEvent
from app.models.deep_analysis import DeepAnalysis, DeepAnalysisEvent
from app.models.splice import EventSpliceFeature
from app.schemas.deep_analysis import (
    DeepAnalysisCreate,
    DeepAnalysisListItem,
    DeepAnalysisResponse,
)
from app.schemas.event import SplicingEventResponse
from app.services.splice_features import compute_pwm, iupac_consensus

router = APIRouter(tags=["deep-analyses"])


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
    q = select(SplicingEvent.id, SplicingEvent.fdr, SplicingEvent.inc_level_difference).where(
        SplicingEvent.analysis_id == analysis_id
    )
    rows = (await db.execute(q)).all()

    # Tag each event
    junction_rows: list[DeepAnalysisEvent] = []
    n_sig = 0
    n_not_sig = 0

    for event_id, fdr, inc_level_diff in rows:
        fdr_ok = fdr is not None and fdr <= body.fdr_threshold
        dpsi_ok = (
            inc_level_diff is not None
            and abs(inc_level_diff) >= body.delta_psi_min
        )
        is_sig = fdr_ok and dpsi_ok

        if is_sig:
            n_sig += 1
        else:
            n_not_sig += 1

        junction_rows.append(
            DeepAnalysisEvent(event_id=event_id, is_significant=is_sig)
        )

    deep = DeepAnalysis(
        analysis_id=analysis_id,
        name=name,
        fdr_threshold=body.fdr_threshold,
        pvalue_threshold=body.pvalue_threshold,
        delta_psi_min=body.delta_psi_min,
        modules=body.modules,
        n_significant=n_sig,
        n_not_significant=n_not_sig,
        status="ready",
    )
    deep.events = junction_rows
    db.add(deep)
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
    response_model=list[SplicingEventResponse],
)
async def list_deep_analysis_events(
    deep_analysis_id: uuid.UUID,
    significant: bool | None = Query(None, description="Filter by significance"),
    db: AsyncSession = Depends(get_db),
):
    """Return events associated with this deep analysis, optionally filtered by significance."""
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

    q = q.order_by(SplicingEvent.fdr.asc().nulls_last())
    rows = (await db.execute(q)).scalars().all()
    return rows


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


class StatTestResult(BaseModel):
    feature: str
    test_name: str
    statistic: float | None = None
    p_value: float | None = None
    significant: bool = False  # p < 0.05

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
    """Welch's t-test for unequal variances. Returns (t_stat, p_value) or (None, None)."""
    n1, n2 = len(vals1), len(vals2)
    if n1 < 2 or n2 < 2:
        return None, None
    m1, m2 = statistics.mean(vals1), statistics.mean(vals2)
    v1 = statistics.variance(vals1)
    v2 = statistics.variance(vals2)
    se = math.sqrt(v1 / n1 + v2 / n2)
    if se == 0:
        return None, None
    t_stat = (m1 - m2) / se
    # Welch-Satterthwaite degrees of freedom
    num = (v1 / n1 + v2 / n2) ** 2
    denom = (v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1)
    df = num / denom if denom > 0 else 1
    # Two-tailed p-value using t-distribution approximation
    p = _t_cdf_approx(abs(t_stat), df) * 2
    return round(t_stat, 4), round(min(p, 1.0), 4)


def _t_cdf_approx(t: float, df: float) -> float:
    """Approximate upper-tail p-value for Student t-distribution.
    Uses the regularized incomplete beta function approximation."""
    x = df / (df + t * t)
    # Regularized incomplete beta function approximation via continued fraction
    a, b = df / 2.0, 0.5
    return 0.5 * _regularized_beta(x, a, b)


def _regularized_beta(x: float, a: float, b: float, max_iter: int = 200) -> float:
    """Regularized incomplete beta function I_x(a,b) via Lentz's continued fraction."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    # Use the log-beta prefix
    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(a * math.log(x) + b * math.log(1 - x) - lbeta) / a

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
        if abs(delta - 1.0) < 1e-8:
            break
    return front * f


def _proportion_z_test(k1: int, n1: int, k2: int, n2: int) -> tuple[float | None, float | None]:
    """Two-proportion z-test. Returns (z_stat, p_value) or (None, None)."""
    if n1 < 1 or n2 < 1:
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
    """Standard normal CDF approximation (Abramowitz & Stegun)."""
    return 0.5 * math.erfc(-x / math.sqrt(2))


def _compute_stat_tests(
    sig_events: list,
    sig_feats: list,
    nonsig_events: list,
    nonsig_feats: list,
) -> list[StatTestResult]:
    """Compute statistical tests comparing significant vs non-significant groups."""
    results: list[StatTestResult] = []

    # 1. Mean ΔΨ — Welch's t-test
    dpsi_sig = [ev.inc_level_difference for ev in sig_events if ev.inc_level_difference is not None]
    dpsi_ns = [ev.inc_level_difference for ev in nonsig_events if ev.inc_level_difference is not None]
    t_stat, p_val = _welch_t_test(dpsi_sig, dpsi_ns)
    results.append(StatTestResult(
        feature="mean_delta_psi", test_name="Welch's t-test",
        statistic=t_stat, p_value=p_val, significant=(p_val or 1) < 0.05,
    ))

    # 2. Exon size — Welch's t-test
    sizes_sig = [f.exon_size for f in sig_feats if f.exon_size is not None]
    sizes_ns = [f.exon_size for f in nonsig_feats if f.exon_size is not None]
    t_stat, p_val = _welch_t_test(sizes_sig, sizes_ns)
    results.append(StatTestResult(
        feature="exon_size", test_name="Welch's t-test",
        statistic=t_stat, p_value=p_val, significant=(p_val or 1) < 0.05,
    ))

    # 3. PPT score — Welch's t-test
    ppt_sig = [f.ppt_score for f in sig_feats if f.ppt_score is not None and f.donor_seq]
    ppt_ns = [f.ppt_score for f in nonsig_feats if f.ppt_score is not None and f.donor_seq]
    t_stat, p_val = _welch_t_test(ppt_sig, ppt_ns)
    results.append(StatTestResult(
        feature="ppt_score", test_name="Welch's t-test",
        statistic=t_stat, p_value=p_val, significant=(p_val or 1) < 0.05,
    ))

    # 4. Canonical GT (5'SS) — proportion z-test
    sig_with_seq = [f for f in sig_feats if f.donor_seq and len(f.donor_seq) >= 9]
    ns_with_seq = [f for f in nonsig_feats if f.donor_seq and len(f.donor_seq) >= 9]
    k1 = sum(1 for f in sig_with_seq if f.donor_is_gt)
    k2 = sum(1 for f in ns_with_seq if f.donor_is_gt)
    z_stat, p_val = _proportion_z_test(k1, len(sig_with_seq), k2, len(ns_with_seq))
    results.append(StatTestResult(
        feature="canonical_gt", test_name="Proportion z-test",
        statistic=z_stat, p_value=p_val, significant=(p_val or 1) < 0.05,
    ))

    # 5. Canonical AG (3'SS) — proportion z-test
    sig_acc = [f for f in sig_feats if f.acceptor_seq and len(f.acceptor_seq) >= 23]
    ns_acc = [f for f in nonsig_feats if f.acceptor_seq and len(f.acceptor_seq) >= 23]
    k1 = sum(1 for f in sig_acc if f.acceptor_is_ag)
    k2 = sum(1 for f in ns_acc if f.acceptor_is_ag)
    z_stat, p_val = _proportion_z_test(k1, len(sig_acc), k2, len(ns_acc))
    results.append(StatTestResult(
        feature="canonical_ag", test_name="Proportion z-test",
        statistic=z_stat, p_value=p_val, significant=(p_val or 1) < 0.05,
    ))

    # 6. In-frame proportion — proportion z-test
    sig_frame = [f for f in sig_feats if f.frame_class and f.frame_class != "unknown"]
    ns_frame = [f for f in nonsig_feats if f.frame_class and f.frame_class != "unknown"]
    k1 = sum(1 for f in sig_frame if f.frame_class == "in_frame")
    k2 = sum(1 for f in ns_frame if f.frame_class == "in_frame")
    z_stat, p_val = _proportion_z_test(k1, len(sig_frame), k2, len(ns_frame))
    results.append(StatTestResult(
        feature="in_frame_pct", test_name="Proportion z-test",
        statistic=z_stat, p_value=p_val, significant=(p_val or 1) < 0.05,
    ))

    # 7. Branch point found — proportion z-test
    k1 = sum(1 for f in sig_with_seq if f.bp_motif_found)
    k2 = sum(1 for f in ns_with_seq if f.bp_motif_found)
    z_stat, p_val = _proportion_z_test(k1, len(sig_with_seq), k2, len(ns_with_seq))
    results.append(StatTestResult(
        feature="bp_found", test_name="Proportion z-test",
        statistic=z_stat, p_value=p_val, significant=(p_val or 1) < 0.05,
    ))

    # 8. Upstream donor GT (flanking exon) — proportion z-test
    sig_up = [f for f in sig_feats if f.upstream_donor_seq and len(f.upstream_donor_seq) >= 9]
    ns_up = [f for f in nonsig_feats if f.upstream_donor_seq and len(f.upstream_donor_seq) >= 9]
    k1 = sum(1 for f in sig_up if f.upstream_donor_is_gt)
    k2 = sum(1 for f in ns_up if f.upstream_donor_is_gt)
    z_stat, p_val = _proportion_z_test(k1, len(sig_up), k2, len(ns_up))
    results.append(StatTestResult(
        feature="upstream_canonical_gt", test_name="Proportion z-test",
        statistic=z_stat, p_value=p_val, significant=(p_val or 1) < 0.05,
    ))

    # 9. Downstream acceptor AG (flanking exon) — proportion z-test
    sig_dn = [f for f in sig_feats if f.downstream_acceptor_seq and len(f.downstream_acceptor_seq) >= 23]
    ns_dn = [f for f in nonsig_feats if f.downstream_acceptor_seq and len(f.downstream_acceptor_seq) >= 23]
    k1 = sum(1 for f in sig_dn if f.downstream_acceptor_is_ag)
    k2 = sum(1 for f in ns_dn if f.downstream_acceptor_is_ag)
    z_stat, p_val = _proportion_z_test(k1, len(sig_dn), k2, len(ns_dn))
    results.append(StatTestResult(
        feature="downstream_canonical_ag", test_name="Proportion z-test",
        statistic=z_stat, p_value=p_val, significant=(p_val or 1) < 0.05,
    ))

    return results


def _compute_group_stats(
    events: list[SplicingEvent],
    feats: list[EventSpliceFeature],
) -> GroupPatternStats:
    """Compute pattern statistics for a group of events."""
    feats_with_seq = [f for f in feats if f.donor_seq]

    # Exon sizes
    sizes = [f.exon_size for f in feats if f.exon_size is not None]

    # Donor
    donor_9 = [f.donor_seq[:9] for f in feats_with_seq if f.donor_seq and len(f.donor_seq) >= 9]
    n_gt = sum(1 for f in feats_with_seq if f.donor_seq and len(f.donor_seq) >= 9 and f.donor_is_gt)

    # Acceptor
    acc_23 = [f.acceptor_seq[-23:] for f in feats_with_seq if f.acceptor_seq and len(f.acceptor_seq) >= 23]
    n_ag = sum(1 for f in feats_with_seq if f.acceptor_seq and len(f.acceptor_seq) >= 23 and f.acceptor_is_ag)

    # Upstream donor (flanking exon)
    up_donor_9 = [f.upstream_donor_seq[:9] for f in feats_with_seq if f.upstream_donor_seq and len(f.upstream_donor_seq) >= 9]
    n_up_gt = sum(1 for f in feats_with_seq if f.upstream_donor_seq and f.upstream_donor_is_gt)

    # Downstream acceptor (flanking exon)
    dn_acc_23 = [f.downstream_acceptor_seq[-23:] for f in feats_with_seq if f.downstream_acceptor_seq and len(f.downstream_acceptor_seq) >= 23]
    n_dn_ag = sum(1 for f in feats_with_seq if f.downstream_acceptor_seq and f.downstream_acceptor_is_ag)

    # PPT
    ppt_scores = [f.ppt_score for f in feats_with_seq if f.ppt_score is not None]

    # Frame
    fc = Counter(f.frame_class or "unknown" for f in feats)

    # Branch point
    bp_total = len(feats_with_seq)
    bp_found = sum(1 for f in feats_with_seq if f.bp_motif_found)

    # Mean ΔΨ
    dpsi = [ev.inc_level_difference for ev in events if ev.inc_level_difference is not None]

    return GroupPatternStats(
        n_events=len(events),
        n_se_with_features=len(feats),
        exon_size_mean=round(statistics.mean(sizes), 1) if sizes else None,
        exon_size_median=round(statistics.median(sizes), 1) if sizes else None,
        pct_canonical_gt=round(n_gt / len(donor_9) * 100, 1) if donor_9 else None,
        pct_canonical_ag=round(n_ag / len(acc_23) * 100, 1) if acc_23 else None,
        ppt_mean_score=round(statistics.mean(ppt_scores), 3) if ppt_scores else None,
        frame_in_frame=fc.get("in_frame", 0),
        frame_frameshift=fc.get("frameshift", 0),
        frame_non_coding=fc.get("non_coding", 0),
        bp_found_pct=round(bp_found / bp_total * 100, 1) if bp_total else None,
        donor_pwm=compute_pwm(donor_9) if donor_9 else None,
        acceptor_pwm=compute_pwm(acc_23) if acc_23 else None,
        donor_consensus=iupac_consensus(donor_9) if donor_9 else None,
        acceptor_consensus=iupac_consensus(acc_23) if acc_23 else None,
        pct_upstream_gt=round(n_up_gt / len(up_donor_9) * 100, 1) if up_donor_9 else None,
        pct_downstream_ag=round(n_dn_ag / len(dn_acc_23) * 100, 1) if dn_acc_23 else None,
        upstream_donor_pwm=compute_pwm(up_donor_9) if up_donor_9 else None,
        downstream_acceptor_pwm=compute_pwm(dn_acc_23) if dn_acc_23 else None,
        upstream_donor_consensus=iupac_consensus(up_donor_9) if up_donor_9 else None,
        downstream_acceptor_consensus=iupac_consensus(dn_acc_23) if dn_acc_23 else None,
        mean_delta_psi=round(statistics.mean(dpsi), 3) if dpsi else None,
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
    z_stat: float | None = None
    p_value: float | None = None
    p_adjusted: float | None = None
    significant: bool = False


class HnRNPMotifResponse(BaseModel):
    n_sig_events: int
    n_bg_events: int
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
    from app.services.hnrnp_motifs import (
        SERegions, define_se_regions, compare_groups, scan_group,
    )
    from app.services.sequence import extract_regions_batch, reverse_complement
    from app.config import settings

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

    def _build_regions(events: list[SplicingEvent]) -> list[SERegions]:
        """Extract five genomic regions per event and fetch sequences."""
        if not events:
            return []
        all_bed_regions: list[tuple[str, int, int]] = []
        event_indices: list[tuple[int, str]] = []  # (event_idx, strand)
        for i, ev in enumerate(events):
            if not ev.chr or ev.exon_start is None or ev.exon_end is None:
                # Placeholder — 5 empty regions
                for _ in range(5):
                    all_bed_regions.append(("", 0, 0))
                event_indices.append((i, ev.strand or "+"))
                continue
            bed = define_se_regions(
                ev.chr, ev.strand or "+",
                ev.exon_start, ev.exon_end,
                ev.upstream_es, ev.upstream_ee,
                ev.downstream_es, ev.downstream_ee,
            )
            all_bed_regions.extend(bed)
            event_indices.append((i, ev.strand or "+"))

        seqs = extract_regions_batch(all_bed_regions, settings.GRCH38_FASTA)

        results: list[SERegions] = []
        for idx, (_, strand) in enumerate(event_indices):
            s = seqs[idx * 5 : idx * 5 + 5]
            if strand == "-":
                s = [reverse_complement(x) if x else "" for x in s]
            results.append(SERegions(
                upstream_exon=s[0],
                upstream_intron=s[1],
                skipped_exon=s[2],
                downstream_intron=s[3],
                downstream_exon=s[4],
            ))
        return results

    import asyncio

    sig_regions = await asyncio.to_thread(_build_regions, sig_events)
    bg_regions = await asyncio.to_thread(_build_regions, bg_events)

    sig_scan = await asyncio.to_thread(scan_group, sig_regions)
    bg_scan = await asyncio.to_thread(scan_group, bg_regions)
    enrichment = await asyncio.to_thread(compare_groups, sig_scan, bg_scan)

    return HnRNPMotifResponse(
        n_sig_events=len(sig_events),
        n_bg_events=len(bg_events),
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

    import asyncio
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
