import { BASE, fetchJSON } from "./client";
import type {
  SpliceFeatureResponse,
  ComputeJobResponse,
  PatternAnalysisResponse,
  MANETranscriptResponse,
  PermutationResponse,
} from "@/types/splice";

export function getEventSpliceFeature(eventId: string): Promise<SpliceFeatureResponse> {
  return fetchJSON<SpliceFeatureResponse>(`${BASE}/splice/feature/${eventId}`);
}

export function computeSpliceFeatures(analysisId: string): Promise<ComputeJobResponse> {
  return fetchJSON<ComputeJobResponse>(`${BASE}/splice/compute/${analysisId}`, {
    method: "POST",
  });
}

export function getSplicePatterns(
  analysisId: string,
  fdrThreshold = 0.05,
  absDeltaPsiMin = 0.05,
  deepAnalysisId?: string,
): Promise<PatternAnalysisResponse> {
  const params = new URLSearchParams({
    fdr_threshold: String(fdrThreshold),
    abs_delta_psi_min: String(absDeltaPsiMin),
  });
  if (deepAnalysisId) params.set("deep_analysis_id", deepAnalysisId);
  return fetchJSON<PatternAnalysisResponse>(
    `${BASE}/splice/patterns/${analysisId}?${params}`,
  );
}

export function getMANETranscript(eventId: string): Promise<MANETranscriptResponse> {
  return fetchJSON<MANETranscriptResponse>(`${BASE}/splice/mane_transcript/${eventId}`);
}

export interface ComputeProgress {
  n_se_events: number;
  n_computed: number;
  pct: number;
  done: boolean;
}

export function getComputeProgress(analysisId: string): Promise<ComputeProgress> {
  return fetchJSON<ComputeProgress>(`${BASE}/splice/progress/${analysisId}`);
}

export function runPermutationTest(
  analysisId: string,
  nIterations: number = 500,
): Promise<PermutationResponse> {
  return fetchJSON<PermutationResponse>(
    `${BASE}/splice/permutation/${analysisId}?n_iterations=${nIterations}`,
    { method: "POST" },
  );
}
