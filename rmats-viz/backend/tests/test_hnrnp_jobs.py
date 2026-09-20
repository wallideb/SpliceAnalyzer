"""
Tests for app.services.hnrnp_jobs: background hnRNP enrichment jobs with an
in-process cache (the fix for the request-timeout failures of the hnRNP panel
and of the deep-analysis PDF on ~100 k-event datasets).

Run:  python -m pytest tests/test_hnrnp_jobs.py -v
"""

from __future__ import annotations

import threading
import uuid
from types import SimpleNamespace

import pytest

from app.services import hnrnp_jobs
from app.services.hnrnp_motifs import REGION_NAMES, SERegions


def _event(chrom="chr1", strand="+"):
    return SimpleNamespace(
        chr=chrom, strand=strand, exon_start=1000, exon_end=1100,
        upstream_es=500, upstream_ee=600, downstream_es=1500, downstream_ee=1600,
    )


@pytest.fixture(autouse=True)
def _clean_registry():
    hnrnp_jobs.reset()
    yield
    hnrnp_jobs.reset()


def _fake_regions(events, fasta_path=None, label="", progress=None):
    """Stand-in for build_se_regions: no samtools, deterministic sequences."""
    out = []
    n = len(REGION_NAMES)
    for i, _ in enumerate(events, start=1):
        seqs = {r: "TAGGGA" + "ACGT" * 10 for r in REGION_NAMES}
        out.append(SERegions(**seqs))
        if progress is not None:
            progress(i * n)
    return out


@pytest.mark.asyncio
async def test_job_runs_to_completion_and_caches(monkeypatch):
    monkeypatch.setattr("app.services.hnrnp_motifs.build_se_regions", _fake_regions)
    did = uuid.uuid4()
    sig = [_event() for _ in range(6)]
    bg = [_event(strand="-") for _ in range(8)]
    loads = 0

    async def load():
        nonlocal loads
        loads += 1
        return sig, bg

    job = await hnrnp_jobs.get_or_start(did, load)
    assert loads == 1
    assert await hnrnp_jobs.wait(job, 10)
    assert job.status == "done", job.error
    assert job.progress == 1.0
    assert job.result["n_sig_events"] == 6 and job.result["n_bg_events"] == 8
    assert len(job.result["results"]) == 19 * 7
    assert job.result["regions"] == list(REGION_NAMES)
    row = job.result["results"][0]
    assert {"motif_name", "protein", "region", "sig_hit_count", "bg_hit_count",
            "sig_density", "bg_density", "p_adjusted", "density_p_adjusted",
            "regulatory_effect"} <= set(row)

    # Second call reuses the finished job without reloading events
    again = await hnrnp_jobs.get_or_start(did, load)
    assert again is job and loads == 1
    assert await hnrnp_jobs.wait(again, 0)


@pytest.mark.asyncio
async def test_running_job_reports_progress_and_is_reused(monkeypatch):
    release = threading.Event()

    def slow_regions(events, fasta_path=None, label="", progress=None):
        release.wait(5)
        return _fake_regions(events, fasta_path, label, progress)

    monkeypatch.setattr("app.services.hnrnp_motifs.build_se_regions", slow_regions)
    did = uuid.uuid4()

    async def load():
        return [_event()] * 3, [_event()] * 3

    job = await hnrnp_jobs.get_or_start(did, load)
    assert job.status == "running" and job.stage == "extract"
    assert not await hnrnp_jobs.wait(job, 0.05)   # bounded wait, still running
    st = job.state()
    assert st["status"] == "running" and 0.0 <= st["progress"] < 1.0
    assert st["n_sig_events"] == 3 and st["n_bg_events"] == 3
    # A concurrent caller gets the same job (single flight)
    assert await hnrnp_jobs.get_or_start(did, load) is job
    release.set()
    assert await hnrnp_jobs.wait(job, 10)
    assert job.status == "done"


@pytest.mark.asyncio
async def test_error_is_kept_and_retry_restarts(monkeypatch):
    calls = 0

    def failing(events, fasta_path=None, label="", progress=None):
        nonlocal calls
        calls += 1
        if calls <= 2:  # both groups of the first run fail
            raise RuntimeError("samtools exploded")
        return _fake_regions(events, fasta_path, label, progress)

    monkeypatch.setattr("app.services.hnrnp_motifs.build_se_regions", failing)
    did = uuid.uuid4()

    async def load():
        return [_event()] * 2, [_event()] * 2

    job = await hnrnp_jobs.get_or_start(did, load)
    assert await hnrnp_jobs.wait(job, 10)
    assert job.status == "error" and "samtools exploded" in job.error
    # Without retry the failed job is returned as is
    assert await hnrnp_jobs.get_or_start(did, load) is job
    # With retry a new job is started and succeeds
    job2 = await hnrnp_jobs.get_or_start(did, load, retry=True)
    assert job2 is not job
    assert await hnrnp_jobs.wait(job2, 10)
    assert job2.status == "done", job2.error
    # retry on a finished job is a no-op
    assert await hnrnp_jobs.get_or_start(did, load, retry=True) is job2


@pytest.mark.asyncio
async def test_events_are_snapshotted_and_discard_forgets(monkeypatch):
    seen: list = []

    def capture(events, fasta_path=None, label="", progress=None):
        seen.extend(events)
        return _fake_regions(events, fasta_path, label, progress)

    monkeypatch.setattr("app.services.hnrnp_motifs.build_se_regions", capture)
    did = uuid.uuid4()
    orm_like = _event(chrom="chrX", strand="-")

    async def load():
        return [orm_like], []

    job = await hnrnp_jobs.get_or_start(did, load)
    assert await hnrnp_jobs.wait(job, 10)
    assert job.status == "done", job.error
    assert all(isinstance(e, hnrnp_jobs.EventCoords) for e in seen)
    assert seen[0].chr == "chrX" and seen[0].strand == "-" and seen[0].upstream_ee == 600
    hnrnp_jobs.discard(did)
    assert hnrnp_jobs.get_job(did) is None
    hnrnp_jobs.discard(did)  # idempotent


def test_stage_progress_is_monotonic_and_bounded():
    job = hnrnp_jobs.HnrnpJob(deep_analysis_id=uuid.uuid4(), n_sig_events=1, n_bg_events=1)
    sp = hnrnp_jobs._StageProgress(job, "scan", {"sig": 10, "bg": 10})
    assert job.stage == "scan" and job.progress == pytest.approx(0.40)
    sp.callback("sig")(5)
    assert job.progress == pytest.approx(0.40 + 0.30 * 0.25)
    sp.callback("bg")(10)
    sp.callback("sig")(10)
    assert job.progress == pytest.approx(0.70)
    sp.callback("sig")(999)  # over-reporting is clamped
    assert job.progress == pytest.approx(0.70)
    assert sum(hnrnp_jobs.STAGE_WEIGHTS.values()) == pytest.approx(1.0)


def test_progress_callbacks_of_service_functions():
    """scan_group / compare_groups / extract_regions_batch call back as documented."""
    from app.services import hnrnp_motifs as hm
    from app.services.sequence import extract_regions_batch

    regions = _fake_regions([_event()] * 2500)
    seen: list[int] = []
    res = hm.scan_group(regions, progress=seen.append)
    assert seen == [1000, 2000, 2500]
    assert len(res) == 19 * 7

    pairs: list[int] = []
    hm.compare_groups(res, res, progress=pairs.append)
    assert pairs == list(range(1, 19 * 7 + 1))

    # No valid region: the callback still reports completion
    done: list[int] = []
    assert extract_regions_batch([("chr1", 5, 5)], "/nonexistent.fa", progress=done.append) == [""]
    assert done == [1]
