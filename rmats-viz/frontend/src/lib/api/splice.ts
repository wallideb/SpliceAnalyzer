import { BASE, fetchJSON } from "./client";
import type {
  SpliceFeatureResponse,
  ComputeJobResponse,
  PatternAnalysisResponse,
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
