"""Background hnRNP motif-enrichment jobs with an in-process result cache.

Why a job and not a plain request handler
-----------------------------------------
The enrichment (``services/hnrnp_motifs``) extracts 7 regions per SE event
with ``samtools faidx``, scans 19 motifs per region and runs a rank test per
(motif, region) pair on the per-event densities.  On a ~100 k-event rMATS
run that is ~700 k sequence extractions and ~13 M regex scans: several
minutes of CPU, far longer than a browser request survives behind a reverse
proxy (Codespaces port forwarding, nginx defaults, ...).  Running it inside
``GET /deep-analyses/{id}/hnrnp-motifs`` therefore failed on large datasets
(the client saw a cut connection, the server kept computing for nothing).

Design
------
* One job per deep analysis, keyed by its UUID.  The first request starts
  the job (``get_or_start``); later requests only read its state.
* Work runs in worker threads via ``asyncio.to_thread`` so the event loop
  stays responsive; the ``progress`` callbacks of the service functions feed
  a 0-1 progress value split by stage (extract / scan / compare).
* The finished payload (a JSON-ready dict, 133 rows) is kept in memory for
  the lifetime of the worker process: the result is deterministic for a given
  deep analysis (its significance tags are fixed at creation) and FASTA, so
  it never needs recomputing.  A failed job is kept too, with its error, and
  can be restarted explicitly (``retry=True``).
* ``wait`` lets callers long-poll for a bounded time so that small datasets
  still get their result in a single request (the E2E suite relies on this).

Events are snapshotted into plain ``EventCoords`` records before the job
starts: the job outlives the request's database session, and it must not
touch detached ORM instances (nor keep 100 k of them alive).
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Iterable

logger = logging.getLogger(__name__)

# Share of the overall progress attributed to each stage.  Measured on a
# synthetic 99.5 k-event dataset: regex scan ≈ 65 s, rank tests ≈ 60 s,
# samtools extraction of ~700 k regions of the same order (I/O bound).
STAGE_WEIGHTS = {"extract": 0.40, "scan": 0.30, "compare": 0.30}
STAGES = ("extract", "scan", "compare")


@dataclass
class EventCoords:
    """The rMATS SE coordinates ``build_se_regions`` needs, detached from the ORM."""

    chr: str | None
    strand: str | None
    exon_start: int | None
    exon_end: int | None
    upstream_es: int | None
    upstream_ee: int | None
    downstream_es: int | None
    downstream_ee: int | None

    @classmethod
    def from_event(cls, ev) -> "EventCoords":
        return cls(
            chr=ev.chr, strand=ev.strand,
            exon_start=ev.exon_start, exon_end=ev.exon_end,
            upstream_es=ev.upstream_es, upstream_ee=ev.upstream_ee,
            downstream_es=ev.downstream_es, downstream_ee=ev.downstream_ee,
        )


@dataclass
class HnrnpJob:
    deep_analysis_id: uuid.UUID
    n_sig_events: int
    n_bg_events: int
    status: str = "running"          # running | done | error
    stage: str = "extract"           # extract | scan | compare
    progress: float = 0.0            # 0..1 overall
    result: dict | None = None       # JSON-ready payload when status == "done"
    error: str | None = None         # message when status == "error"
    started_at: float = field(default_factory=time.monotonic)
    finished_at: float | None = None
    _done: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    _task: asyncio.Task | None = field(default=None, repr=False)

    @property
    def elapsed_seconds(self) -> float:
        end = self.finished_at if self.finished_at is not None else time.monotonic()
        return round(end - self.started_at, 1)

    def state(self) -> dict:
        """Status payload (without the result rows)."""
        return {
            "status": self.status,
            "stage": self.stage,
            "progress": round(self.progress, 4),
            "error": self.error,
            "elapsed_seconds": self.elapsed_seconds,
            "n_sig_events": self.n_sig_events,
            "n_bg_events": self.n_bg_events,
        }


_jobs: dict[uuid.UUID, HnrnpJob] = {}


def get_job(deep_analysis_id: uuid.UUID) -> HnrnpJob | None:
    return _jobs.get(deep_analysis_id)


def discard(deep_analysis_id: uuid.UUID) -> None:
    """Forget a job (deep analysis deleted).  A running task finishes on its own."""
    _jobs.pop(deep_analysis_id, None)


def reset() -> None:
    """Drop every cached job (tests)."""
    _jobs.clear()


def serialize_enrichment(
    enrichment: Iterable, n_sig: int, n_bg: int, regions: list[str], effects: dict,
) -> dict:
    """JSON-ready payload shared by the API response and the PDF report."""
    return {
        "n_sig_events": n_sig,
        "n_bg_events": n_bg,
        "regions": list(regions),
        "results": [
            {
                "motif_name": r.motif_name,
                "protein": r.protein,
                "region": r.region,
                "sig_hit_count": r.sig_hit_count,
                "sig_total": r.sig_total,
                "bg_hit_count": r.bg_hit_count,
                "bg_total": r.bg_total,
                "sig_density": r.sig_density,
                "bg_density": r.bg_density,
                "z_stat": r.z_stat,
                "p_value": r.p_value,
                "p_adjusted": r.p_adjusted,
                "significant": r.significant,
                "density_u_stat": r.density_u_stat,
                "density_p_value": r.density_p_value,
                "density_p_adjusted": r.density_p_adjusted,
                "density_significant": bool(r.density_significant),
                "regulatory_effect": effects.get(r.protein, {}).get(r.region),
            }
            for r in enrichment
        ],
    }


class _StageProgress:
    """Thread-safe accumulator turning per-group callbacks into job progress.

    Two groups (significant / background) are processed concurrently, each
    reporting an absolute count for its own group; the job progress is the
    stage weight × (sum of the groups' counts / stage total).
    """

    def __init__(self, job: HnrnpJob, stage: str, totals: dict[str, int]):
        self.job = job
        self.stage = stage
        self.totals = totals
        self.total = max(1, sum(totals.values()))
        self.counts = {k: 0 for k in totals}
        self.lock = threading.Lock()
        self.base = sum(STAGE_WEIGHTS[s] for s in STAGES[: STAGES.index(stage)])
        job.stage = stage
        job.progress = self.base

    def callback(self, group: str) -> Callable[[int], None]:
        def _cb(count: int) -> None:
            with self.lock:
                self.counts[group] = min(count, self.totals[group])
                frac = sum(self.counts.values()) / self.total
                self.job.progress = self.base + STAGE_WEIGHTS[self.stage] * min(1.0, frac)
        return _cb


async def _run(job: HnrnpJob, sig: list[EventCoords], bg: list[EventCoords]) -> None:
    from app.services.hnrnp_motifs import (
        REGION_NAMES, REGULATORY_EFFECTS, build_se_regions, compare_groups, scan_group,
    )

    n_regions = len(REGION_NAMES)
    try:
        t0 = time.monotonic()
        sp = _StageProgress(job, "extract", {"sig": len(sig) * n_regions, "bg": len(bg) * n_regions})
        sig_regions, bg_regions = await asyncio.gather(
            asyncio.to_thread(build_se_regions, sig, None, "sig", sp.callback("sig")),
            asyncio.to_thread(build_se_regions, bg, None, "bg", sp.callback("bg")),
        )
        t1 = time.monotonic()
        sp = _StageProgress(job, "scan", {"sig": len(sig), "bg": len(bg)})
        sig_scan, bg_scan = await asyncio.gather(
            asyncio.to_thread(scan_group, sig_regions, sp.callback("sig")),
            asyncio.to_thread(scan_group, bg_regions, sp.callback("bg")),
        )
        del sig_regions, bg_regions
        t2 = time.monotonic()
        sp = _StageProgress(job, "compare", {"pairs": len(sig_scan)})
        enrichment = await asyncio.to_thread(compare_groups, sig_scan, bg_scan, sp.callback("pairs"))
        t3 = time.monotonic()
        job.result = serialize_enrichment(
            enrichment, len(sig), len(bg), list(REGION_NAMES), REGULATORY_EFFECTS,
        )
        job.status = "done"
        job.progress = 1.0
        logger.info(
            "hnRNP job %s done: %d sig + %d bg SE events in %.1fs "
            "(extract %.1fs, scan %.1fs, compare %.1fs)",
            job.deep_analysis_id, len(sig), len(bg), t3 - t0, t1 - t0, t2 - t1, t3 - t2,
        )
    except Exception as exc:  # noqa: BLE001 — surfaced to the client as job.error
        logger.exception("hnRNP job %s failed", job.deep_analysis_id)
        job.status = "error"
        job.error = f"{type(exc).__name__}: {exc}"
    finally:
        job.finished_at = time.monotonic()
        job._done.set()


def start_job(deep_analysis_id: uuid.UUID, sig_events: list, bg_events: list) -> HnrnpJob:
    """Start (or restart) the job for *deep_analysis_id* and return it.

    *sig_events* / *bg_events* may be ORM instances or anything exposing the
    rMATS SE attributes; they are snapshotted before the task starts.
    """
    sig = [EventCoords.from_event(e) for e in sig_events]
    bg = [EventCoords.from_event(e) for e in bg_events]
    job = HnrnpJob(deep_analysis_id=deep_analysis_id, n_sig_events=len(sig), n_bg_events=len(bg))
    _jobs[deep_analysis_id] = job
    job._task = asyncio.get_running_loop().create_task(_run(job, sig, bg))
    logger.info(
        "hnRNP job %s started: %d sig + %d bg SE events", deep_analysis_id, len(sig), len(bg),
    )
    return job


async def get_or_start(
    deep_analysis_id: uuid.UUID,
    load_events: Callable[[], Awaitable[tuple[list, list]]],
    retry: bool = False,
) -> HnrnpJob:
    """Return the job for *deep_analysis_id*, starting it when none exists.

    *load_events* is only awaited when a job has to be started; it returns
    ``(significant SE events, background SE events)``.  With ``retry=True`` a
    job that ended in error is discarded and started again; a running or
    finished job is always reused.
    """
    job = _jobs.get(deep_analysis_id)
    if job is not None and not (retry and job.status == "error"):
        return job
    sig_events, bg_events = await load_events()
    return start_job(deep_analysis_id, sig_events, bg_events)


async def wait(job: HnrnpJob, timeout: float) -> bool:
    """Wait up to *timeout* seconds for *job* to finish; True when it has."""
    if job.status != "running":
        return True
    if timeout <= 0:
        return False
    try:
        await asyncio.wait_for(job._done.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    return job.status != "running"
