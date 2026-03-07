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

import asyncio
import logging
import statistics
import uuid
from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
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
    IntronSizeStats,
    SiteStats,
    PPTStats,
    FrameStats,
    ClusterInfo,
    MetricPermResult,
    PermutationResponse,
)
from app.services.event_cluster import cluster_se_events
from app.services.mane import annotate_mane, get_transcript_exons
from app.services.permutation import run_permutation
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


# Limit concurrent Ensembl + samtools calls to avoid overwhelming external services
_COMPUTE_SEM = asyncio.Semaphore(10)


async def _fetch_features(
    event: SplicingEvent,
    fa_ok: bool,
) -> tuple[Any, dict]:
    """Pure-compute step (no DB): extract sequences + call Ensembl.

    Runs under _COMPUTE_SEM so at most 10 events are processed concurrently.
    Returns (SpliceFeatureResult, mane_dict).
    """
    async with _COMPUTE_SEM:
        windows = None
        if fa_ok and event.exon_start is not None and event.exon_end is not None:
            try:
                windows = await asyncio.to_thread(
                    get_splice_windows,
                    event.chr or "",
                    event.strand or "+",
                    event.exon_start,
                    event.exon_end,
                )
            except Exception as exc:
                logger.warning("sequence extraction failed for %s: %s", event.id, exc)

        feat_data = compute_features(event, windows)

        mane: dict = {}
        if event.gene_id:
            try:
                mane = await asyncio.to_thread(
                    annotate_mane,
                    event.gene_id,
                    event.chr or "",
                    event.strand or "+",
                    event.exon_start or 0,
                    event.exon_end or 0,
                )
            except Exception as exc:
                logger.warning("MANE lookup failed for %s: %s", event.gene_id, exc)

        return feat_data, mane


async def _upsert_feature(
    event: SplicingEvent,
    feat_data: Any,
    mane: dict,
    db: AsyncSession,
) -> EventSpliceFeature:
    """DB write step (sequential, single session)."""
    # Determine frame_class: prefer MANE-based result; fall back to exon-size
    # divisibility when MANE lookup was not available (Ensembl unreachable,
    # gene_id missing, or no MANE transcript found).
    mane_frame_class = mane.get("frame_class", "unknown") or "unknown"
    if mane_frame_class in ("unknown", None) and feat_data.exon_size is not None:
        mane_frame_class = "in_frame" if feat_data.exon_size % 3 == 0 else "frameshift"

    values: dict = dict(
        event_id               = event.id,
        exon_size              = feat_data.exon_size,
        upstream_intron_size   = feat_data.upstream_intron_size,
        downstream_intron_size = feat_data.downstream_intron_size,
        donor_seq              = feat_data.donor_seq or None,
        acceptor_seq           = feat_data.acceptor_seq or None,
        ppt_seq                = feat_data.ppt_seq or None,
        donor_is_gt            = feat_data.donor_is_gt,
        acceptor_is_ag         = feat_data.acceptor_is_ag,
        ppt_score              = feat_data.ppt_score,
        ppt_longest_run        = feat_data.ppt_longest_run,
        bp_motif_found         = feat_data.bp_motif_found,
        bp_distance            = feat_data.bp_distance,
        bp_score               = feat_data.bp_score,
        mane_transcript_id     = mane.get("transcript_id"),
        exon_rank              = mane.get("exon_rank"),
        frame_region           = mane.get("frame_region", "unknown"),
        frame_class            = mane_frame_class,
        cds_exon_length        = mane.get("cds_exon_length"),
    )
    stmt = (
        pg_insert(EventSpliceFeature)
        .values(id=uuid.uuid4(), **values)
        .on_conflict_do_update(index_elements=["event_id"], set_=values)
        .returning(EventSpliceFeature)
    )
    result = await db.execute(stmt)
    return result.scalar_one()


async def _compute_one(
    event: SplicingEvent,
    db: AsyncSession,
    fa_ok: bool,
) -> EventSpliceFeature:
    """Compute features for a single SE event (used by the per-event GET endpoint)."""
    feat_data, mane = await _fetch_features(event, fa_ok)
    return await _upsert_feature(event, feat_data, mane, db)


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

    # 1. Fetch all features in parallel (Ensembl + samtools), then write sequentially.
    #    _fetch_features is capped at _COMPUTE_SEM concurrent tasks; DB writes stay
    #    on the single AsyncSession to avoid concurrent-session errors.
    fetch_results = await asyncio.gather(
        *[_fetch_features(ev, fa_ok) for ev in se_events],
        return_exceptions=True,
    )

    n_computed = 0
    for ev, res in zip(se_events, fetch_results):
        if isinstance(res, Exception):
            logger.error("Feature compute failed for %s: %s", ev.id, res)
            continue
        try:
            feat_data, mane = res
            await _upsert_feature(ev, feat_data, mane, db)
            n_computed += 1
        except Exception as exc:
            logger.error("DB write failed for %s: %s", ev.id, exc)

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
    fdr_threshold: float = Query(0.05, ge=0.0, le=1.0, description="FDR significance cutoff"),
    abs_delta_psi_min: float = Query(0.05, ge=0.0, le=1.0, description="Minimum |ΔΨ| for significance"),
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

    # ── Intron sizes ─────────────────────────────────────────────────────────
    up_sizes   = [f.upstream_intron_size   for f in all_feats if f.upstream_intron_size   is not None]
    down_sizes = [f.downstream_intron_size for f in all_feats if f.downstream_intron_size is not None]
    upstream_intron_stats = IntronSizeStats(
        median = round(statistics.median(up_sizes),   1) if up_sizes   else None,
        mean   = round(statistics.mean(up_sizes),     1) if up_sizes   else None,
    )
    downstream_intron_stats = IntronSizeStats(
        median = round(statistics.median(down_sizes), 1) if down_sizes else None,
        mean   = round(statistics.mean(down_sizes),   1) if down_sizes else None,
    )

    # ── Significance tagging ─────────────────────────────────────────────────
    n_significant = 0
    n_not_significant = 0
    delta_psi_significant: list[float] = []
    for ev, _ in rows:
        fdr_ok  = ev.fdr is not None and ev.fdr <= fdr_threshold
        dpsi_ok = (
            ev.inc_level_difference is not None
            and abs(ev.inc_level_difference) >= abs_delta_psi_min
        )
        if fdr_ok and dpsi_ok:
            n_significant += 1
            delta_psi_significant.append(ev.inc_level_difference)  # type: ignore[arg-type]
        else:
            n_not_significant += 1

    # ── Mean ΔΨ ──────────────────────────────────────────────────────────────
    delta_psi_list = [
        ev.inc_level_difference
        for ev, _ in rows
        if ev.inc_level_difference is not None
    ]
    mean_delta_psi = round(statistics.mean(delta_psi_list), 3) if delta_psi_list else None
    mean_delta_psi_significant = (
        round(statistics.mean(delta_psi_significant), 3) if delta_psi_significant else None
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
        analysis_id                 = str(analysis_id),
        n_se_events                 = len(rows),
        n_analyzed                  = len(feats_with_seq),
        clusters                    = ClusterInfo(
            n_raw_events = len(rows),
            n_clusters   = len(clusters),
        ),
        fasta_available             = bool(feats_with_seq),
        fdr_threshold               = fdr_threshold,
        abs_delta_psi_min           = abs_delta_psi_min,
        n_significant               = n_significant,
        n_not_significant           = n_not_significant,
        exon_sizes                  = exon_stats,
        upstream_intron_sizes       = upstream_intron_stats,
        downstream_intron_sizes     = downstream_intron_stats,
        mean_delta_psi              = mean_delta_psi,
        mean_delta_psi_significant  = mean_delta_psi_significant,
        donor_sites                 = donor_stats,
        acceptor_sites              = acc_stats,
        ppt                         = ppt_stats,
        frame                       = frame_stats,
        bp_found_pct                = bp_pct,
    )

# ---------------------------------------------------------------------------
# GET /splice/mane_transcript/{event_id}
# ---------------------------------------------------------------------------

@router.get("/mane_transcript/{event_id}")
async def get_mane_transcript(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return the full MANE Select transcript exon structure for a SE event.

    Used by the MANETranscriptTrack frontend component to draw the linear
    transcript diagram with the skipped exon highlighted.

    Response fields:
      transcript_id  — Ensembl transcript accession (or null)
      exons          — list of {start, end, size} sorted by position (0-based)
      n_exons        — total exon count in the MANE transcript
      exon_rank      — 1-based rank of the skipped exon in the transcript
      strand         — '+' or '-'
      skipped_start  — genomic start of the skipped exon (0-based)
      skipped_end    — genomic end of the skipped exon
    """
    ev_res = await db.execute(
        select(SplicingEvent).where(SplicingEvent.id == event_id)
    )
    event = ev_res.scalar_one_or_none()
    if event is None:
        raise HTTPException(404, "Event not found")

    feat_res = await db.execute(
        select(EventSpliceFeature).where(EventSpliceFeature.event_id == event_id)
    )
    feat = feat_res.scalar_one_or_none()

    if feat is None or not feat.mane_transcript_id:
        return {
            "transcript_id": None,
            "exons": [],
            "n_exons": 0,
            "exon_rank": None,
            "strand": event.strand,
            "skipped_start": event.exon_start,
            "skipped_end": event.exon_end,
        }

    exons = await asyncio.to_thread(get_transcript_exons, feat.mane_transcript_id)

    return {
        "transcript_id": feat.mane_transcript_id,
        "exons": exons,
        "n_exons": len(exons),
        "exon_rank": feat.exon_rank,
        "strand": event.strand,
        "skipped_start": event.exon_start,
        "skipped_end": event.exon_end,
    }

# ---------------------------------------------------------------------------
# POST /splice/permutation/{analysis_id}
# ---------------------------------------------------------------------------

@router.post("/permutation/{analysis_id}", response_model=PermutationResponse)
async def run_permutation_test(
    analysis_id: uuid.UUID,
    n_iterations: int = 500,
    db: AsyncSession = Depends(get_db),
):
    """Run a permutation test for all SE events of an analysis.

    For each SE event, the patient/control group labels are randomly shuffled
    *n_iterations* times and ΔΨ is recomputed.  The empirical p-value is the
    fraction of permutations where |permuted ΔΨ| ≥ |observed ΔΨ|.

    Parameters
    ----------
    n_iterations : number of permutation iterations (default 500, max 2000).

    Response
    --------
    • events            — per-event results (observed ΔΨ, empirical p-value)
    • global_null_hist  — null distribution histogram (all events × iterations)
    • observed_hist     — observed ΔΨ histogram (for overlay comparison)
    • pct_p05 / pct_p01 — % events significant at p < 0.05 / 0.01
    """
    n_iterations = min(max(n_iterations, 10), 2000)

    result = await db.execute(
        select(SplicingEvent).where(
            SplicingEvent.analysis_id == analysis_id,
            SplicingEvent.event_type == "SE",
        )
    )
    se_events = list(result.scalars().all())

    if not se_events:
        raise HTTPException(404, "No SE events found for this analysis")

    # Fetch splice features for metric permutation tests
    event_ids = [ev.id for ev in se_events]
    feat_result = await db.execute(
        select(EventSpliceFeature).where(
            EventSpliceFeature.event_id.in_(event_ids)
        )
    )
    features_by_id = {str(f.event_id): f for f in feat_result.scalars().all()}
    # Build parallel list (None if feature not computed for that event)
    features_list = [features_by_id.get(str(ev.id)) for ev in se_events]

    perm_result = await asyncio.to_thread(
        run_permutation, se_events, features_list, n_iterations
    )

    return PermutationResponse(
        analysis_id             = str(analysis_id),
        n_iterations            = perm_result.n_iterations,
        n_events_tested         = perm_result.n_events_tested,
        events                  = [
            {
                "event_id":           r.event_id,
                "gene_symbol":        r.gene_symbol,
                "observed_delta_psi": r.observed_delta_psi,
                "empirical_p_value":  r.empirical_p_value,
                "n1":                 r.n1,
                "n2":                 r.n2,
                "null_hist_bins":     r.null_hist_bins,
                "null_hist_counts":   r.null_hist_counts,
            }
            for r in perm_result.events
        ],
        global_null_hist_bins   = perm_result.global_null_hist_bins,
        global_null_hist_counts = perm_result.global_null_hist_counts,
        observed_hist_bins      = perm_result.observed_hist_bins,
        observed_hist_counts    = perm_result.observed_hist_counts,
        pct_p05                 = perm_result.pct_p05,
        pct_p01                 = perm_result.pct_p01,
        metric_results          = [
            MetricPermResult(
                metric_name       = r.metric_name,
                label             = r.label,
                observed_stat     = r.observed_stat,
                empirical_p_value = r.empirical_p_value,
                n_valid           = r.n_valid,
                n_g1              = r.n_g1,
                n_g2              = r.n_g2,
                null_hist_bins    = r.null_hist_bins,
                null_hist_counts  = r.null_hist_counts,
            )
            for r in perm_result.metric_results
        ],
    )
