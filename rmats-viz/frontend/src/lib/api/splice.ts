import { fetchJSON } from "./client";
import type {
  SpliceFeatureResponse,
  ComputeJobResponse,
  PatternAnalysisResponse,
} from "@/types/splice";

export function getEventSpliceFeature(eventId: string): Promise<SpliceFeatureResponse> {
  return fetchJSON<SpliceFeatureResponse>(`/splice/feature/${eventId}`);
}

export function computeSpliceFeatures(analysisId: string): Promise<ComputeJobResponse> {
  return fetchJSON<ComputeJobResponse>(`/splice/compute/${analysisId}`, {
    method: "POST",
  });
}

export function getSplicePatterns(analysisId: string): Promise<PatternAnalysisResponse> {
  return fetchJSON<PatternAnalysisResponse>(`/splice/patterns/${analysisId}`);
}
