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

import statistics
import uuid
from collections import Counter
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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

    # Auto-name if not provided
    name = body.name or f"Deep analysis — FDR≤{body.fdr_threshold} |ΔΨ|≥{body.delta_psi_min}"

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
        pval_ok = True  # p-value filter is optional
        dpsi_ok = (
            inc_level_diff is not None
            and abs(inc_level_diff) >= body.delta_psi_min
        )
        is_sig = fdr_ok and pval_ok and dpsi_ok

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
    mean_delta_psi: float | None = None


class PatternComparisonResponse(BaseModel):
    significant: GroupPatternStats
    not_significant: GroupPatternStats


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
    )


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
        mean_delta_psi=round(statistics.mean(dpsi), 3) if dpsi else None,
    )
