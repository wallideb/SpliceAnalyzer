"""
Pydantic schemas for the splice pattern analysis endpoints.
"""
from __future__ import annotations

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
    # sequences (skipped exon splice sites)
    donor_seq: str | None = None
    acceptor_seq: str | None = None
    ppt_seq: str | None = None
    # sequences (flanking exon splice sites)
    upstream_donor_seq: str | None = None
    downstream_acceptor_seq: str | None = None
    # GT-AG (skipped exon)
    donor_is_gt: bool | None = None
    acceptor_is_ag: bool | None = None
    # GT-AG (flanking exons)
    upstream_donor_is_gt: bool | None = None
    downstream_acceptor_is_ag: bool | None = None
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
    sequence_source: str | None = None   # "fasta" | "ensembl" | None
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


class EventPermResult(BaseModel):
    event_id: str
    gene_symbol: str | None = None
    observed_delta_psi: float | None = None
    empirical_p_value: float | None = None
    n1: int = 0
    n2: int = 0
    null_hist_bins: list[float] = []
    null_hist_counts: list[int] = []


class MetricPermResult(BaseModel):
    """Permutation result for a single scalar metric (PPT, exon size, frame, canonical)."""
    metric_name: str
    label: str
    observed_stat: float | None = None
    empirical_p_value: float | None = None
    n_valid: int = 0
    n_g1: int = 0
    n_g2: int = 0
    null_hist_bins: list[float] = []
    null_hist_counts: list[int] = []


class PermutationResponse(BaseModel):
    analysis_id: str
    n_iterations: int
    n_events_tested: int
    n_total_events: int = 0   # total SE events permuted (before significance filter)
    events: list[EventPermResult] = []
    global_null_hist_bins: list[float] = []
    global_null_hist_counts: list[int] = []
    observed_hist_bins: list[float] = []
    observed_hist_counts: list[int] = []
    pct_p05: float | None = None
    pct_p01: float | None = None
    metric_results: list[MetricPermResult] = []


class PatternAnalysisResponse(BaseModel):
    analysis_id: str
    n_se_events: int
    n_analyzed: int          # events with FASTA sequences
    clusters: ClusterInfo
    fasta_available: bool
    # Significance thresholds applied
    fdr_threshold: float = 0.05
    abs_delta_psi_min: float = 0.05
    n_significant: int = 0       # events passing both thresholds
    n_not_significant: int = 0   # events failing at least one threshold
    exon_sizes: ExonSizeStats
    upstream_intron_sizes: IntronSizeStats = IntronSizeStats()
    downstream_intron_sizes: IntronSizeStats = IntronSizeStats()
    mean_delta_psi: float | None = None
    mean_delta_psi_significant: float | None = None   # mean ΔΨ for significant events only
    donor_sites: SiteStats
    acceptor_sites: SiteStats
    ppt: PPTStats
    frame: FrameStats
    bp_found_pct: float | None = None   # % events with a branch-point match
    # Flanking exon splice sites
    upstream_donor_sites: SiteStats | None = None
    downstream_acceptor_sites: SiteStats | None = None
