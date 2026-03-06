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

export function getSplicePatterns(analysisId: string): Promise<PatternAnalysisResponse> {
  return fetchJSON<PatternAnalysisResponse>(`${BASE}/splice/patterns/${analysisId}`);
}

export function getMANETranscript(eventId: string): Promise<MANETranscriptResponse> {
  return fetchJSON<MANETranscriptResponse>(`${BASE}/splice/mane_transcript/${eventId}`);
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
