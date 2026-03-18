/**
 * Deep-analysis API client
 * =========================
 * CRUD for saved deep analyses and their events.
 */

import { fetchJSON, BASE } from "./client";
import type { SplicingEvent } from "@/types/event";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface DeepAnalysisCreate {
  name?: string;
  fdr_threshold: number;
  pvalue_threshold?: number;
  delta_psi_min: number;
  modules: string[];
}

export interface DeepAnalysisResponse {
  id: string;
  analysis_id: string;
  name: string;
  status: string;
  fdr_threshold: number;
  pvalue_threshold: number | null;
  delta_psi_min: number;
  modules: string[];
  n_significant: number;
  n_not_significant: number;
  permutation_iterations: number | null;
  created_at: string;
}

export interface DeepAnalysisListItem {
  id: string;
  name: string;
  status: string;
  fdr_threshold: number;
  delta_psi_min: number;
  n_significant: number;
  n_not_significant: number;
  created_at: string;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export function createDeepAnalysis(
  analysisId: string,
  body: DeepAnalysisCreate,
): Promise<DeepAnalysisResponse> {
  return fetchJSON(`${BASE}/analyses/${analysisId}/deep-analyses`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function listDeepAnalyses(
  analysisId: string,
): Promise<DeepAnalysisListItem[]> {
  return fetchJSON(`${BASE}/analyses/${analysisId}/deep-analyses`);
}

export function getDeepAnalysis(
  deepId: string,
): Promise<DeepAnalysisResponse> {
  return fetchJSON(`${BASE}/deep-analyses/${deepId}`);
}

export function deleteDeepAnalysis(deepId: string): Promise<void> {
  return fetch(`${BASE}/deep-analyses/${deepId}`, { method: "DELETE" }).then(
    (r) => {
      if (!r.ok) throw new Error(`Delete failed: ${r.status}`);
    },
  );
}

export function getDeepAnalysisEvents(
  deepId: string,
  significant?: boolean,
): Promise<SplicingEvent[]> {
  const params = significant !== undefined ? `?significant=${significant}` : "";
  return fetchJSON(`${BASE}/deep-analyses/${deepId}/events${params}`);
}

// ---------------------------------------------------------------------------
// Pattern comparison
// ---------------------------------------------------------------------------

export interface GroupPatternStats {
  n_events: number;
  n_se_with_features: number;
  exon_size_mean: number | null;
  exon_size_median: number | null;
  pct_canonical_gt: number | null;
  pct_canonical_ag: number | null;
  ppt_mean_score: number | null;
  frame_in_frame: number;
  frame_frameshift: number;
  frame_non_coding: number;
  bp_found_pct: number | null;
  donor_pwm: Array<{ A: number; C: number; G: number; T: number }> | null;
  acceptor_pwm: Array<{ A: number; C: number; G: number; T: number }> | null;
  donor_consensus: string | null;
  acceptor_consensus: string | null;
  // Flanking exon splice sites
  pct_upstream_gt: number | null;
  pct_downstream_ag: number | null;
  upstream_donor_pwm: Array<{ A: number; C: number; G: number; T: number }> | null;
  downstream_acceptor_pwm: Array<{ A: number; C: number; G: number; T: number }> | null;
  upstream_donor_consensus: string | null;
  downstream_acceptor_consensus: string | null;
  mean_delta_psi: number | null;
  // Flanking intron sizes
  upstream_intron_size_mean: number | null;
  upstream_intron_size_median: number | null;
  downstream_intron_size_mean: number | null;
  downstream_intron_size_median: number | null;
}

export interface StatTestResult {
  feature: string;
  test_name: string;
  statistic: number | null;
  p_value: number | null;
  significant: boolean;
}

export interface PatternComparisonResponse {
  significant: GroupPatternStats;
  not_significant: GroupPatternStats;
  statistical_tests: StatTestResult[];
}

export function getPatternComparison(
  deepId: string,
): Promise<PatternComparisonResponse> {
  return fetchJSON(`${BASE}/deep-analyses/${deepId}/pattern-comparison`);
}
