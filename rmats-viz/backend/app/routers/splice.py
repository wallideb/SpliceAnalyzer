"""
Splice pattern analysis router
================================
Endpoints:
  POST /api/v1/splice/compute/{analysis_id}
      Compute splice features for every SE event in the analysis.
      Idempotent: re-running overwrites existing feature rows.
      Returns a summary (no body needed).

  GET  /api/v1/splice/feature/{event_id}
      Return pre-computed splice features for one event.
      If not yet computed, triggers on-the-fly computation.

  GET  /api/v1/splice/patterns/{analysis_id}
      Aggregate pattern analysis across all SE events with features.
      Uses clusters to avoid double-counting near-identical events.
"""

from __future__ import annotations

import logging
import statistics
import uuid
from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.event import SplicingEvent
from app.models.splice import EventCluster, EventSpliceFeature
from app.schemas.splice import (
    ComputeJobResponse,
    SpliceFeatureResponse,
    PatternAnalysisResponse,
    ExonSizeStats,
    SiteStats,
    PPTStats,
    FrameStats,
    ClusterInfo,
)
from app.services.event_cluster import cluster_se_events
from app.services.mane import annotate_mane
from app.services.sequence import fasta_available, get_splice_windows
from app.services.splice_features import compute_features, compute_pwm, iupac_consensus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/splice", tags=["splice"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _feat_to_response(feat: EventSpliceFeature, event: SplicingEvent) -> SpliceFeatureResponse:
    return SpliceFeatureResponse(
        event_id=str(event.id),
        event_type=event.event_type,
        gene_symbol=event.gene_symbol,
        chr=event.chr,
        strand=event.strand,
        exon_size=feat.exon_size,
        upstream_intron_size=feat.upstream_intron_size,
        downstream_intron_size=feat.downstream_intron_size,
        donor_seq=feat.donor_seq,
        acceptor_seq=feat.acceptor_seq,
        ppt_seq=feat.ppt_seq,
        donor_is_gt=feat.donor_is_gt,
        acceptor_is_ag=feat.acceptor_is_ag,
        ppt_score=feat.ppt_score,
        ppt_longest_run=feat.ppt_longest_run,
        bp_motif_found=feat.bp_motif_found,
        bp_distance=feat.bp_distance,
        bp_score=feat.bp_score,
        mane_transcript_id=feat.mane_transcript_id,
        exon_rank=feat.exon_rank,
        frame_region=feat.frame_region,
        frame_class=feat.frame_class,
        cds_exon_length=feat.cds_exon_length,
        fasta_available=bool(feat.donor_seq),
    )


async def _compute_one(
    event: SplicingEvent,
    db: AsyncSession,
    fa_ok: bool,
) -> EventSpliceFeature:
    """Compute (or recompute) features for a single SE event. DB write included."""
    windows = None
    if fa_ok and event.exon_start is not None and event.exon_end is not None:
        try:
            windows = get_splice_windows(
                chrom=event.chr or "",
                strand=event.strand or "+",
                exon_start=event.exon_start,
                exon_end=event.exon_end,
            )
        except Exception as exc:
            logger.warning("sequence extraction failed for %s: %s", event.id, exc)

    feat_data = compute_features(event, windows)

    # MANE annotation (network call, cached in SQLite)
    mane: dict = {}
    if event.gene_id:
        try:
            mane = annotate_mane(
                gene_id=event.gene_id,
                chrom=event.chr or "",
                strand=event.strand or "+",
                exon_start=event.exon_start or 0,
                exon_end=event.exon_end or 0,
            )
        except Exception as exc:
            logger.warning("MANE lookup failed for %s: %s", event.gene_id, exc)

    # Atomic upsert — avoids UniqueViolationError when the bulk POST and a
    # per-event GET run concurrently and both see feat=None before inserting.
    values: dict = dict(
        event_id            = event.id,
        exon_size           = feat_data.exon_size,
        upstream_intron_size   = feat_data.upstream_intron_size,
        downstream_intron_size = feat_data.downstream_intron_size,
        donor_seq           = feat_data.donor_seq or None,
        acceptor_seq        = feat_data.acceptor_seq or None,
        ppt_seq             = feat_data.ppt_seq or None,
        donor_is_gt         = feat_data.donor_is_gt,
        acceptor_is_ag      = feat_data.acceptor_is_ag,
        ppt_score           = feat_data.ppt_score,
        ppt_longest_run     = feat_data.ppt_longest_run,
        bp_motif_found      = feat_data.bp_motif_found,
        bp_distance         = feat_data.bp_distance,
        bp_score            = feat_data.bp_score,
        mane_transcript_id  = mane.get("transcript_id"),
        exon_rank           = mane.get("exon_rank"),
        frame_region        = mane.get("frame_region", "unknown"),
        frame_class         = mane.get("frame_class", "unknown"),
        cds_exon_length     = mane.get("cds_exon_length"),
    )
    stmt = (
        pg_insert(EventSpliceFeature)
        .values(id=uuid.uuid4(), **values)
        .on_conflict_do_update(
            index_elements=["event_id"],
            set_=values,
        )
        .returning(EventSpliceFeature)
    )
    result = await db.execute(stmt)
    feat = result.scalar_one()
    return feat


# ---------------------------------------------------------------------------
# POST /splice/compute/{analysis_id}
# ---------------------------------------------------------------------------

@router.post("/compute/{analysis_id}", response_model=ComputeJobResponse)
async def compute_splice_features(
    analysis_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Compute splice features + clusters for all SE events of an analysis."""
    # Fetch all SE events
    result = await db.execute(
        select(SplicingEvent).where(
            SplicingEvent.analysis_id == analysis_id,
            SplicingEvent.event_type == "SE",
        )
    )
    se_events = result.scalars().all()

    if not se_events:
        raise HTTPException(404, "No SE events found for this analysis")

    fa_ok = fasta_available()

    # 1. Compute per-event features
    n_computed = 0
    for ev in se_events:
        try:
            await _compute_one(ev, db, fa_ok)
            n_computed += 1
        except Exception as exc:
            logger.error("Feature compute failed for %s: %s", ev.id, exc)

    # 2. Cluster events
    clusters = cluster_se_events(se_events)

    # 3. Persist clusters (delete previous, re-insert)
    await db.execute(
        delete(EventCluster).where(EventCluster.analysis_id == analysis_id)
    )
    for cl in clusters:
        rep_id = uuid.UUID(cl.rep_event_id) if cl.rep_event_id else None
        db.add(EventCluster(
            id=cl.cluster_id,
            analysis_id=analysis_id,
            gene_symbol=cl.gene_symbol,
            chr=cl.chr,
            strand=cl.strand,
            exon_start=cl.exon_start,
            exon_end=cl.exon_end,
            n_events=cl.n_events,
            source_ids=[str(i) for i in cl.source_ids],
            rep_event_id=rep_id,
        ))

    await db.commit()

    return ComputeJobResponse(
        analysis_id=str(analysis_id),
        n_se_events=len(se_events),
        n_computed=n_computed,
        n_clusters=len(clusters),
        fasta_available=fa_ok,
        message=(
            f"Computed features for {n_computed}/{len(se_events)} SE events "
            f"→ {len(clusters)} canonical clusters."
            + (" (FASTA not available — sizes only)" if not fa_ok else "")
        ),
    )


# ---------------------------------------------------------------------------
# GET /splice/feature/{event_id}
# ---------------------------------------------------------------------------

@router.get("/feature/{event_id}", response_model=SpliceFeatureResponse)
async def get_splice_feature(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return splice features for one SE event (compute on-the-fly if missing)."""
    ev_res = await db.execute(
        select(SplicingEvent).where(SplicingEvent.id == event_id)
    )
    event = ev_res.scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found")
    if event.event_type != "SE":
        return SpliceFeatureResponse(
            event_id=str(event_id),
            event_type=event.event_type,
            gene_symbol=event.gene_symbol,
            error="Splice site analysis only available for SE events",
        )

    # Check cache
    feat_res = await db.execute(
        select(EventSpliceFeature).where(EventSpliceFeature.event_id == event_id)
    )
    feat = feat_res.scalar_one_or_none()

    if feat is None:
        fa_ok = fasta_available()
        feat = await _compute_one(event, db, fa_ok)
        await db.commit()

    return _feat_to_response(feat, event)


# ---------------------------------------------------------------------------
# GET /splice/patterns/{analysis_id}
# ---------------------------------------------------------------------------

@router.get("/patterns/{analysis_id}", response_model=PatternAnalysisResponse)
async def get_splice_patterns(
    analysis_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Aggregate splice-signal patterns across all SE events of an analysis."""

    # Fetch events + their features (join)
    from sqlalchemy import join as sqljoin
    stmt = (
        select(SplicingEvent, EventSpliceFeature)
        .join(
            EventSpliceFeature,
            EventSpliceFeature.event_id == SplicingEvent.id,
            isouter=True,
        )
        .where(
            SplicingEvent.analysis_id == analysis_id,
            SplicingEvent.event_type == "SE",
        )
    )
    rows = (await db.execute(stmt)).all()

    if not rows:
        raise HTTPException(404, "No SE events (with features) for this analysis")

    # Cluster count
    cl_res = await db.execute(
        select(EventCluster).where(EventCluster.analysis_id == analysis_id)
    )
    clusters = cl_res.scalars().all()

    # Collect features that were successfully computed (have donor_seq)
    feats_with_seq: list[EventSpliceFeature] = []
    all_feats: list[EventSpliceFeature] = []
    for _, feat in rows:
        if feat is not None:
            all_feats.append(feat)
            if feat.donor_seq:
                feats_with_seq.append(feat)

    # ── Exon sizes (all events with computed size) ──────────────────────────
    sizes = [f.exon_size for f in all_feats if f.exon_size is not None]
    size_dist: Counter[int] = Counter()
    for s in sizes:
        bucket = min(500, (s // 25) * 25)
        size_dist[bucket] += 1

    exon_stats = ExonSizeStats(
        mean   = round(statistics.mean(sizes),   1) if sizes else None,
        median = round(statistics.median(sizes), 1) if sizes else None,
        min    = min(sizes) if sizes else None,
        max    = max(sizes) if sizes else None,
        distribution = [{"bin": k, "count": v} for k, v in sorted(size_dist.items())],
    )

    # ── Donor (5'SS) ────────────────────────────────────────────────────────
    donor_seqs = [f.donor_seq for f in feats_with_seq if f.donor_seq and len(f.donor_seq) >= 9]
    donor_9    = [s[:9] for s in donor_seqs]
    n_gt       = sum(1 for f in feats_with_seq if f.donor_is_gt)

    donor_stats = SiteStats(
        n_sequences   = len(donor_9),
        consensus     = iupac_consensus(donor_9) if donor_9 else None,
        pwm           = compute_pwm(donor_9),
        n_canonical   = n_gt,
        pct_canonical = round(n_gt / len(feats_with_seq) * 100, 1) if feats_with_seq else 0.0,
        examples      = donor_9[:8],
    )

    # ── Acceptor (3'SS) ─────────────────────────────────────────────────────
    acc_seqs = [f.acceptor_seq for f in feats_with_seq if f.acceptor_seq and len(f.acceptor_seq) >= 23]
    acc_23   = [s[-23:] for s in acc_seqs]
    n_ag     = sum(1 for f in feats_with_seq if f.acceptor_is_ag)

    acc_stats = SiteStats(
        n_sequences   = len(acc_23),
        consensus     = iupac_consensus(acc_23) if acc_23 else None,
        pwm           = compute_pwm(acc_23),
        n_canonical   = n_ag,
        pct_canonical = round(n_ag / len(feats_with_seq) * 100, 1) if feats_with_seq else 0.0,
        examples      = acc_23[:8],
    )

    # ── PPT ─────────────────────────────────────────────────────────────────
    ppt_scores = [f.ppt_score for f in feats_with_seq if f.ppt_score is not None]
    ppt_runs   = [f.ppt_longest_run for f in feats_with_seq if f.ppt_longest_run is not None]

    ppt_stats = PPTStats(
        mean_score      = round(statistics.mean(ppt_scores),   3) if ppt_scores else None,
        scores          = ppt_scores[:100],
        mean_longest_run= round(statistics.mean(ppt_runs), 1)    if ppt_runs   else None,
    )

    # ── Frame ────────────────────────────────────────────────────────────────
    fc_counts: Counter[str] = Counter(f.frame_class or "unknown" for f in all_feats)
    frame_stats = FrameStats(
        in_frame   = fc_counts["in_frame"],
        frameshift = fc_counts["frameshift"],
        non_coding = fc_counts["non_coding"],
        unknown    = fc_counts["unknown"],
    )

    # ── Branch-point ─────────────────────────────────────────────────────────
    bp_total = len(feats_with_seq)
    bp_found = sum(1 for f in feats_with_seq if f.bp_motif_found)
    bp_pct   = round(bp_found / bp_total * 100, 1) if bp_total else None

    return PatternAnalysisResponse(
        analysis_id     = str(analysis_id),
        n_se_events     = len(rows),
        n_analyzed      = len(feats_with_seq),
        clusters        = ClusterInfo(
            n_raw_events = len(rows),
            n_clusters   = len(clusters),
        ),
        fasta_available = bool(feats_with_seq),
        exon_sizes      = exon_stats,
        donor_sites     = donor_stats,
        acceptor_sites  = acc_stats,
        ppt             = ppt_stats,
        frame           = frame_stats,
        bp_found_pct    = bp_pct,
    )
