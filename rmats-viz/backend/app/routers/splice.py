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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, get_db
from app.models.event import SplicingEvent
from app.models.deep_analysis import DeepAnalysis, DeepAnalysisEvent
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
from app.services.sequence import fasta_available, get_splice_windows, get_splice_windows_from_ensembl
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
        upstream_donor_seq=feat.upstream_donor_seq,
        downstream_acceptor_seq=feat.downstream_acceptor_seq,
        donor_is_gt=feat.donor_is_gt,
        acceptor_is_ag=feat.acceptor_is_ag,
        upstream_donor_is_gt=feat.upstream_donor_is_gt,
        downstream_acceptor_is_ag=feat.downstream_acceptor_is_ag,
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
        sequence_source=feat.sequence_source,
    )


# Limit concurrent Ensembl + samtools calls to avoid overwhelming external services
_COMPUTE_SEM = asyncio.Semaphore(5)

# Limit total concurrent on-the-fly splice feature requests to prevent OOM/crash
# when the deep analysis page fires dozens of requests simultaneously.
_ENDPOINT_SEM = asyncio.Semaphore(8)


async def _fetch_features(
    event: SplicingEvent,
    fa_ok: bool,
) -> tuple[Any, dict, str | None]:
    """Pure-compute step (no DB): extract sequences + call Ensembl.

    Runs under _COMPUTE_SEM so at most 5 events are processed concurrently.
    Returns (SpliceFeatureResult, mane_dict).
    """
    async with _COMPUTE_SEM:
        windows = None
        coords_ok = event.exon_start is not None and event.exon_end is not None

        # 1. Try local FASTA (fast, offline)
        if fa_ok and coords_ok:
            try:
                windows = await asyncio.to_thread(
                    get_splice_windows,
                    event.chr or "",
                    event.strand or "+",
                    event.exon_start,
                    event.exon_end,
                    None,
                    event.upstream_ee,
                    event.downstream_es,
                )
            except Exception as exc:
                logger.warning("FASTA extraction failed for %s: %s", event.id, exc)

        # 2. Fallback: Ensembl REST API (network, no local files required)
        if windows is None and coords_ok:
            try:
                windows = await asyncio.to_thread(
                    get_splice_windows_from_ensembl,
                    event.chr or "",
                    event.strand or "+",
                    event.exon_start,
                    event.exon_end,
                    event.upstream_ee,
                    event.downstream_es,
                )
                if not windows.donor_seq:   # empty → Ensembl also failed
                    windows = None
            except Exception as exc:
                logger.warning("Ensembl REST fallback failed for %s: %s", event.id, exc)

        feat_data = compute_features(event, windows)
        seq_source: str | None = windows.source if windows is not None else None

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

        return feat_data, mane, seq_source


async def _upsert_feature(
    event: SplicingEvent,
    feat_data: Any,
    mane: dict,
    db: AsyncSession,
    seq_source: str | None = None,
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
        donor_seq               = feat_data.donor_seq or None,
        acceptor_seq            = feat_data.acceptor_seq or None,
        ppt_seq                 = feat_data.ppt_seq or None,
        upstream_donor_seq      = feat_data.upstream_donor_seq or None,
        downstream_acceptor_seq = feat_data.downstream_acceptor_seq or None,
        donor_is_gt            = feat_data.donor_is_gt,
        acceptor_is_ag         = feat_data.acceptor_is_ag,
        upstream_donor_is_gt       = feat_data.upstream_donor_is_gt,
        downstream_acceptor_is_ag  = feat_data.downstream_acceptor_is_ag,
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
        sequence_source        = seq_source,
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
    feat_data, mane, seq_source = await _fetch_features(event, fa_ok)
    return await _upsert_feature(event, feat_data, mane, db, seq_source)


# ---------------------------------------------------------------------------
# POST /splice/compute/{analysis_id}
# ---------------------------------------------------------------------------

_COMPUTE_CHUNK = 50  # events processed concurrently per chunk


async def _run_compute_background(analysis_id: uuid.UUID, fa_ok: bool) -> None:
    """Background task: compute splice features for all SE events.

    Creates its own DB session so it can run after the HTTP response is sent.
    Processes events in chunks to avoid OOM with large analyses (200k+).
    """
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(SplicingEvent).where(
                    SplicingEvent.analysis_id == analysis_id,
                    SplicingEvent.event_type == "SE",
                )
            )
            se_events = result.scalars().all()
            if not se_events:
                return

            n_computed = 0
            n_total = len(se_events)

            # Process in chunks to cap concurrent coroutines and memory usage
            for chunk_start in range(0, n_total, _COMPUTE_CHUNK):
                chunk = se_events[chunk_start : chunk_start + _COMPUTE_CHUNK]
                fetch_results = await asyncio.gather(
                    *[_fetch_features(ev, fa_ok) for ev in chunk],
                    return_exceptions=True,
                )
                for ev, res in zip(chunk, fetch_results):
                    if isinstance(res, Exception):
                        logger.error("Feature compute failed for %s: %s", ev.id, res)
                        continue
                    try:
                        feat_data, mane, seq_source = res
                        await _upsert_feature(ev, feat_data, mane, db, seq_source)
                        n_computed += 1
                    except Exception as exc:
                        logger.error("DB write failed for %s: %s", ev.id, exc)

                # Commit after each chunk to release DB resources
                await db.commit()

            clusters = cluster_se_events(se_events)
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
            logger.info("Background compute done: %d/%d SE events for %s", n_computed, n_total, analysis_id)
    except Exception as exc:
        logger.error("Background compute task crashed for %s: %s", analysis_id, exc)


@router.post("/compute/{analysis_id}", response_model=ComputeJobResponse, status_code=202)
async def compute_splice_features(
    analysis_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Trigger background computation of splice features + clusters.

    Returns 202 Accepted immediately; the actual work runs in the background.
    Poll GET /splice/patterns/{analysis_id} to know when data is available.
    """
    # Quick validation — check SE events exist
    count_res = await db.execute(
        select(SplicingEvent).where(
            SplicingEvent.analysis_id == analysis_id,
            SplicingEvent.event_type == "SE",
        ).limit(1)
    )
    if not count_res.scalar_one_or_none():
        raise HTTPException(404, "No SE events found for this analysis")

    fa_ok = fasta_available()
    background_tasks.add_task(_run_compute_background, analysis_id, fa_ok)

    return ComputeJobResponse(
        analysis_id=str(analysis_id),
        n_se_events=0,   # unknown at this point — computation is async
        n_computed=0,
        n_clusters=0,
        fasta_available=fa_ok,
        message="Computation started in background. Poll /splice/progress/{id} for progress.",
    )


# ---------------------------------------------------------------------------
# GET /splice/progress/{analysis_id}
# ---------------------------------------------------------------------------

@router.get("/progress/{analysis_id}")
async def get_compute_progress(
    analysis_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return splice feature computation progress for an analysis."""
    from sqlalchemy import func

    n_se_result = await db.execute(
        select(func.count(SplicingEvent.id)).where(
            SplicingEvent.analysis_id == analysis_id,
            SplicingEvent.event_type == "SE",
        )
    )
    n_se = n_se_result.scalar() or 0

    n_computed_result = await db.execute(
        select(func.count(EventSpliceFeature.id)).where(
            EventSpliceFeature.event_id.in_(
                select(SplicingEvent.id).where(
                    SplicingEvent.analysis_id == analysis_id,
                    SplicingEvent.event_type == "SE",
                )
            )
        )
    )
    n_computed = n_computed_result.scalar() or 0

    return {
        "n_se_events": n_se,
        "n_computed": n_computed,
        "pct": round(n_computed / n_se * 100, 1) if n_se > 0 else 0,
        "done": n_computed >= n_se,
    }


# ---------------------------------------------------------------------------
# GET /splice/feature/{event_id}
# ---------------------------------------------------------------------------

@router.get("/feature/{event_id}", response_model=SpliceFeatureResponse)
async def get_splice_feature(event_id: uuid.UUID):
    """Return splice features for one SE event (compute on-the-fly if missing).

    Manages DB sessions manually (no ``Depends(get_db)``) so that the
    connection is released before slow I/O (samtools / Ensembl / MANE).
    This prevents pool exhaustion when 10+ cards load in parallel.

    Uses ``_ENDPOINT_SEM`` to cap total concurrent requests.  When the
    semaphore is full, returns HTTP 503 so the frontend can retry later.
    """
    if not _ENDPOINT_SEM._value:  # noqa: SLF001 – fast non-blocking check
        raise HTTPException(503, "Server busy computing splice features, retry shortly")

    async with _ENDPOINT_SEM:
        return await _get_splice_feature_inner(event_id)


async def _get_splice_feature_inner(event_id: uuid.UUID) -> SpliceFeatureResponse:
    # ── 1. Quick DB read: fetch event + check feature cache ──────────────
    async with AsyncSessionLocal() as db:
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

        feat_res = await db.execute(
            select(EventSpliceFeature).where(EventSpliceFeature.event_id == event_id)
        )
        feat = feat_res.scalar_one_or_none()

        # If feature exists AND already has MANE data (or gene_id is missing),
        # return immediately.  Otherwise retry MANE lookup.
        if feat is not None:
            has_mane = feat.mane_transcript_id is not None
            can_retry_mane = (not has_mane) and bool(event.gene_id)
            if not can_retry_mane:
                return _feat_to_response(feat, event)
            # Retry MANE in background — return current data but schedule update
            _retry_event = event   # snapshot for closure
    # ── session closed — connection returned to pool ─────────────────────

    # ── 2. Slow I/O (no DB held): samtools / Ensembl / MANE ─────────────
    if feat is not None:
        # Retry MANE only (sequences already computed)
        try:
            mane = await asyncio.to_thread(
                annotate_mane,
                _retry_event.gene_id,
                _retry_event.chr or "",
                _retry_event.strand or "+",
                _retry_event.exon_start or 0,
                _retry_event.exon_end or 0,
            )
            if mane.get("transcript_id"):
                async with AsyncSessionLocal() as db:
                    from sqlalchemy import update
                    await db.execute(
                        update(EventSpliceFeature)
                        .where(EventSpliceFeature.event_id == event_id)
                        .values(
                            mane_transcript_id=mane["transcript_id"],
                            exon_rank=mane.get("exon_rank"),
                            frame_region=mane.get("frame_region", "unknown"),
                            frame_class=mane.get("frame_class") or feat.frame_class,
                            cds_exon_length=mane.get("cds_exon_length"),
                        )
                    )
                    await db.commit()
                    # Re-read updated feature
                    feat_res = await db.execute(
                        select(EventSpliceFeature).where(EventSpliceFeature.event_id == event_id)
                    )
                    feat = feat_res.scalar_one()
                    return _feat_to_response(feat, _retry_event)
        except Exception as exc:
            logger.debug("MANE retry failed for %s: %s", event_id, exc)
        return _feat_to_response(feat, _retry_event)

    fa_ok = fasta_available()
    feat_data, mane, seq_source = await _fetch_features(event, fa_ok)

    # ── 3. Persist only if sequences were obtained.  When both FASTA and
    #    Ensembl fail (e.g. FASTA still downloading, network issue), we
    #    return a transient size-only response so the next request retries.
    if seq_source is not None:
        async with AsyncSessionLocal() as db:
            feat = await _upsert_feature(event, feat_data, mane, db, seq_source)
            await db.commit()
        return _feat_to_response(feat, event)

    # Return non-cached size-only placeholder
    return SpliceFeatureResponse(
        event_id=str(event.id),
        event_type=event.event_type,
        gene_symbol=event.gene_symbol,
        chr=event.chr,
        strand=event.strand,
        exon_size=feat_data.exon_size,
        upstream_intron_size=feat_data.upstream_intron_size,
        downstream_intron_size=feat_data.downstream_intron_size,
        fasta_available=False,
        sequence_source=None,
    )


# ---------------------------------------------------------------------------
# GET /splice/patterns/{analysis_id}
# ---------------------------------------------------------------------------

@router.get("/patterns/{analysis_id}", response_model=PatternAnalysisResponse)
async def get_splice_patterns(
    analysis_id: uuid.UUID,
    fdr_threshold: float = Query(0.05, ge=0.0, le=1.0, description="FDR significance cutoff"),
    abs_delta_psi_min: float = Query(0.05, ge=0.0, le=1.0, description="Minimum |ΔΨ| for significance"),
    deep_analysis_id: uuid.UUID | None = Query(None, description="If set, only analyse significant events from this deep analysis"),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate splice-signal patterns across SE events of an analysis.

    When deep_analysis_id is provided, only events tagged as significant
    in that deep analysis are included (thresholds are informational only).
    """

    # Fetch events + their features (join)
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

    # If deep_analysis_id is provided, restrict to significant events only
    if deep_analysis_id is not None:
        stmt = stmt.join(
            DeepAnalysisEvent,
            DeepAnalysisEvent.event_id == SplicingEvent.id,
        ).where(
            DeepAnalysisEvent.deep_analysis_id == deep_analysis_id,
            DeepAnalysisEvent.is_significant == True,
        )

    rows = (await db.execute(stmt)).all()

    if not rows:
        raise HTTPException(404, "No SE events (with features) for this analysis")

    # Cluster count (use SQL count instead of loading all cluster objects)
    from sqlalchemy import func as sqla_func
    cl_count_res = await db.execute(
        select(sqla_func.count(EventCluster.id)).where(EventCluster.analysis_id == analysis_id)
    )
    n_clusters = cl_count_res.scalar() or 0

    # ── Single-pass aggregation over all rows ─────────────────────────────
    # Avoids 7+ separate iterations over 200k rows.
    sizes: list[int] = []
    up_sizes: list[int] = []
    down_sizes: list[int] = []
    size_dist: Counter[int] = Counter()
    donor_9: list[str] = []
    acc_23: list[str] = []
    n_gt = 0
    n_ag = 0
    ppt_scores: list[float] = []
    ppt_runs: list[int] = []
    fc_counts: Counter[str] = Counter()
    bp_found_count = 0
    n_with_seq = 0
    delta_psi_list: list[float] = []
    delta_psi_significant: list[float] = []
    n_significant = 0
    n_not_significant = 0

    for ev, feat in rows:
        # ΔΨ
        if ev.inc_level_difference is not None:
            delta_psi_list.append(ev.inc_level_difference)

        # Significance — must run for ALL events, not just those with features
        if deep_analysis_id is None:
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
        else:
            if ev.inc_level_difference is not None:
                delta_psi_significant.append(ev.inc_level_difference)

        if feat is None:
            continue

        # Frame counts (all feats)
        fc_counts[feat.frame_class or "unknown"] += 1

        # Sizes (all feats)
        if feat.exon_size is not None:
            sizes.append(feat.exon_size)
            bucket = min(500, (feat.exon_size // 25) * 25)
            size_dist[bucket] += 1
        if feat.upstream_intron_size is not None:
            up_sizes.append(feat.upstream_intron_size)
        if feat.downstream_intron_size is not None:
            down_sizes.append(feat.downstream_intron_size)

        # Sequence-dependent metrics
        if feat.donor_seq:
            n_with_seq += 1
            # Donor
            if len(feat.donor_seq) >= 9:
                donor_9.append(feat.donor_seq[:9])
                if feat.donor_is_gt:
                    n_gt += 1
            # Acceptor
            if feat.acceptor_seq and len(feat.acceptor_seq) >= 23:
                acc_23.append(feat.acceptor_seq[-23:])
                if feat.acceptor_is_ag:
                    n_ag += 1
            # PPT
            if feat.ppt_score is not None:
                ppt_scores.append(feat.ppt_score)
            if feat.ppt_longest_run is not None:
                ppt_runs.append(feat.ppt_longest_run)
            # BP
            if feat.bp_motif_found:
                bp_found_count += 1

    # Deep-analysis significance counts
    if deep_analysis_id is not None:
        da_row = await db.execute(
            select(DeepAnalysis).where(DeepAnalysis.id == deep_analysis_id)
        )
        deep_rec = da_row.scalar_one_or_none()
        if deep_rec:
            n_significant = deep_rec.n_significant
            n_not_significant = deep_rec.n_not_significant

    # ── Compute stats ─────────────────────────────────────────────────────
    exon_stats = ExonSizeStats(
        mean   = round(statistics.mean(sizes),   1) if sizes else None,
        median = round(statistics.median(sizes), 1) if sizes else None,
        min    = min(sizes) if sizes else None,
        max    = max(sizes) if sizes else None,
        distribution = [{"bin": k, "count": v} for k, v in sorted(size_dist.items())],
    )
    upstream_intron_stats = IntronSizeStats(
        median = round(statistics.median(up_sizes),   1) if up_sizes   else None,
        mean   = round(statistics.mean(up_sizes),     1) if up_sizes   else None,
    )
    downstream_intron_stats = IntronSizeStats(
        median = round(statistics.median(down_sizes), 1) if down_sizes else None,
        mean   = round(statistics.mean(down_sizes),   1) if down_sizes else None,
    )

    mean_delta_psi = round(statistics.mean(delta_psi_list), 3) if delta_psi_list else None
    mean_delta_psi_significant = (
        round(statistics.mean(delta_psi_significant), 3) if delta_psi_significant else None
    )

    donor_stats = SiteStats(
        n_sequences   = len(donor_9),
        consensus     = iupac_consensus(donor_9) if donor_9 else None,
        pwm           = compute_pwm(donor_9),
        n_canonical   = n_gt,
        pct_canonical = round(n_gt / len(donor_9) * 100, 1) if donor_9 else 0.0,
        examples      = donor_9[:8],
    )
    acc_stats = SiteStats(
        n_sequences   = len(acc_23),
        consensus     = iupac_consensus(acc_23) if acc_23 else None,
        pwm           = compute_pwm(acc_23),
        n_canonical   = n_ag,
        pct_canonical = round(n_ag / len(acc_23) * 100, 1) if acc_23 else 0.0,
        examples      = acc_23[:8],
    )
    ppt_stats = PPTStats(
        mean_score      = round(statistics.mean(ppt_scores),   3) if ppt_scores else None,
        scores          = ppt_scores[:100],
        mean_longest_run= round(statistics.mean(ppt_runs), 1)    if ppt_runs   else None,
    )
    frame_stats = FrameStats(
        in_frame   = fc_counts["in_frame"],
        frameshift = fc_counts["frameshift"],
        non_coding = fc_counts["non_coding"],
        unknown    = fc_counts["unknown"],
    )

    bp_pct = round(bp_found_count / n_with_seq * 100, 1) if n_with_seq else None

    return PatternAnalysisResponse(
        analysis_id                 = str(analysis_id),
        n_se_events                 = len(rows),
        n_analyzed                  = n_with_seq,
        clusters                    = ClusterInfo(
            n_raw_events = len(rows),
            n_clusters   = n_clusters,
        ),
        fasta_available             = bool(n_with_seq),
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
    fdr_threshold: float | None = None,
    delta_psi_min: float | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Run a permutation test for all SE events of an analysis.

    For each SE event, the patient/control group labels are randomly shuffled
    *n_iterations* times and ΔΨ is recomputed.  The empirical p-value is the
    fraction of permutations where |permuted ΔΨ| ≥ |observed ΔΨ|.

    Parameters
    ----------
    n_iterations   : number of permutation iterations (default 500, max 2000).
    fdr_threshold  : optional FDR threshold to count significant events (from deep analysis).
    delta_psi_min  : optional |ΔΨ| minimum to count significant events (from deep analysis).

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

    # Count significant events using deep analysis thresholds (if provided)
    n_total = perm_result.n_events_tested
    if fdr_threshold is not None and delta_psi_min is not None:
        n_sig = sum(
            1 for ev in se_events
            if ev.fdr is not None and ev.fdr <= fdr_threshold
            and ev.inc_level_difference is not None
            and abs(ev.inc_level_difference) >= delta_psi_min
        )
    else:
        n_sig = n_total

    return PermutationResponse(
        analysis_id             = str(analysis_id),
        n_iterations            = perm_result.n_iterations,
        n_events_tested         = n_sig,
        n_total_events          = n_total,
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
