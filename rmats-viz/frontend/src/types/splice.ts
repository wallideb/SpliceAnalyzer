/**
 * Splice pattern analysis types
 * Mirrors app/schemas/splice.py
 */

export interface SpliceFeatureResponse {
  event_id: string;
  event_type: string | null;
  gene_symbol: string | null;
  chr: string | null;
  strand: string | null;
  // sizes
  exon_size: number | null;
  upstream_intron_size: number | null;
  downstream_intron_size: number | null;
  // sequences (skipped exon splice sites)
  donor_seq: string | null;
  acceptor_seq: string | null;
  ppt_seq: string | null;
  // sequences (flanking exon splice sites)
  upstream_donor_seq: string | null;
  downstream_acceptor_seq: string | null;
  // GT-AG (skipped exon)
  donor_is_gt: boolean | null;
  acceptor_is_ag: boolean | null;
  // GT-AG (flanking exons)
  upstream_donor_is_gt: boolean | null;
  downstream_acceptor_is_ag: boolean | null;
  // PPT
  ppt_score: number | null;
  ppt_longest_run: number | null;
  // branch-point
  bp_motif_found: boolean | null;
  bp_distance: number | null;
  bp_score: number | null;
  // MANE
  mane_transcript_id: string | null;
  exon_rank: number | null;
  frame_region: string | null;   // CDS | UTR5 | UTR3 | partial | non_coding | unknown
  frame_class: string | null;    // in_frame | frameshift | non_coding | unknown
  cds_exon_length: number | null;
  // meta
  fasta_available: boolean;
  sequence_source: string | null;  // "fasta" | "ensembl" | null
  error: string | null;
}

export interface ComputeJobResponse {
  analysis_id: string;
  n_se_events: number;
  n_computed: number;
  n_clusters: number;
  fasta_available: boolean;
  message: string;
}

export interface ExonSizeStats {
  mean: number | null;
  median: number | null;
  min: number | null;
  max: number | null;
  distribution: { bin: number; count: number }[];
}

export interface SiteStats {
  n_sequences: number;
  consensus: string | null;
  pwm: Record<"A" | "C" | "G" | "T", number>[];
  n_canonical: number;
  pct_canonical: number;
  examples: string[];
}

export interface PPTStats {
  mean_score: number | null;
  scores: number[];
  mean_longest_run: number | null;
}

export interface FrameStats {
  in_frame: number;
  frameshift: number;
  non_coding: number;
  unknown: number;
}

export interface MANEExon {
  start: number;
  end: number;
  size: number;
}

export interface MANETranscriptResponse {
  transcript_id: string | null;
  exons: MANEExon[];
  n_exons: number;
  exon_rank: number | null;
  strand: string | null;
  skipped_start: number | null;
  skipped_end: number | null;
}

export interface EventPermResult {
  event_id: string;
  gene_symbol: string | null;
  observed_delta_psi: number | null;
  empirical_p_value: number | null;
  n1: number;
  n2: number;
  null_hist_bins: number[];
  null_hist_counts: number[];
}

export interface MetricPermResult {
  metric_name: string;
  label: string;
  observed_stat: number | null;
  empirical_p_value: number | null;
  n_valid: number;
  n_g1: number;
  n_g2: number;
  null_hist_bins: number[];
  null_hist_counts: number[];
}

export interface PermutationResponse {
  analysis_id: string;
  n_iterations: number;
  n_events_tested: number;
  n_total_events: number;
  events: EventPermResult[];
  global_null_hist_bins: number[];
  global_null_hist_counts: number[];
  observed_hist_bins: number[];
  observed_hist_counts: number[];
  pct_p05: number | null;
  pct_p01: number | null;
  metric_results: MetricPermResult[];
}

export interface IntronSizeStats {
  median: number | null;
  mean: number | null;
}

export interface PatternAnalysisResponse {
  analysis_id: string;
  n_se_events: number;
  n_analyzed: number;
  clusters: { n_raw_events: number; n_clusters: number };
  fasta_available: boolean;
  // Significance thresholds
  fdr_threshold: number;
  abs_delta_psi_min: number;
  n_significant: number;
  n_not_significant: number;
  exon_sizes: ExonSizeStats;
  upstream_intron_sizes: IntronSizeStats;
  downstream_intron_sizes: IntronSizeStats;
  mean_delta_psi: number | null;
  mean_delta_psi_significant: number | null;
  donor_sites: SiteStats;
  acceptor_sites: SiteStats;
  // Flanking exon splice sites
  upstream_donor_sites: SiteStats | null;
  downstream_acceptor_sites: SiteStats | null;
  ppt: PPTStats;
  frame: FrameStats;
  bp_found_pct: number | null;
}
