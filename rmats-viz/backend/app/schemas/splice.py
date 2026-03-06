"""
Pydantic schemas for the splice pattern analysis endpoints.
"""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Per-event feature response
# ---------------------------------------------------------------------------

class SpliceFeatureResponse(BaseModel):
    event_id: str
    event_type: str | None = None
    gene_symbol: str | None = None
    chr: str | None = None
    strand: str | None = None
    # sizes
    exon_size: int | None = None
    upstream_intron_size: int | None = None
    downstream_intron_size: int | None = None
    # sequences
    donor_seq: str | None = None
    acceptor_seq: str | None = None
    ppt_seq: str | None = None
    # GT-AG
    donor_is_gt: bool | None = None
    acceptor_is_ag: bool | None = None
    # PPT
    ppt_score: float | None = None
    ppt_longest_run: int | None = None
    # branch-point
    bp_motif_found: bool | None = None
    bp_distance: int | None = None
    bp_score: int | None = None
    # MANE
    mane_transcript_id: str | None = None
    exon_rank: int | None = None
    frame_region: str | None = None
    frame_class: str | None = None
    cds_exon_length: int | None = None
    # status
    fasta_available: bool = False
    error: str | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Compute job response
# ---------------------------------------------------------------------------

class ComputeJobResponse(BaseModel):
    analysis_id: str
    n_se_events: int
    n_computed: int
    n_clusters: int
    fasta_available: bool
    message: str


# ---------------------------------------------------------------------------
# Aggregate pattern analysis
# ---------------------------------------------------------------------------

class IntronSizeStats(BaseModel):
    median: float | None = None
    mean: float | None = None


class ExonSizeStats(BaseModel):
    mean: float | None = None
    median: float | None = None
    min: int | None = None
    max: int | None = None
    distribution: list[dict[str, Any]] = []   # [{bin: int, count: int}]


class SiteStats(BaseModel):
    n_sequences: int = 0
    consensus: str | None = None
    pwm: list[dict[str, float]] = []           # [{A,C,G,T} per position]
    n_canonical: int = 0
    pct_canonical: float = 0.0
    examples: list[str] = []                   # up to 8 raw sequences


class PPTStats(BaseModel):
    mean_score: float | None = None
    scores: list[float] = []
    mean_longest_run: float | None = None


class FrameStats(BaseModel):
    in_frame: int = 0
    frameshift: int = 0
    non_coding: int = 0
    unknown: int = 0


class ClusterInfo(BaseModel):
    n_raw_events: int = 0
    n_clusters: int = 0


class PatternAnalysisResponse(BaseModel):
    analysis_id: str
    n_se_events: int
    n_analyzed: int          # events with FASTA sequences
    clusters: ClusterInfo
    fasta_available: bool
    exon_sizes: ExonSizeStats
    upstream_intron_sizes: IntronSizeStats = IntronSizeStats()
    downstream_intron_sizes: IntronSizeStats = IntronSizeStats()
    mean_delta_psi: float | None = None
    donor_sites: SiteStats
    acceptor_sites: SiteStats
    ppt: PPTStats
    frame: FrameStats
    bp_found_pct: float | None = None   # % events with a branch-point match
