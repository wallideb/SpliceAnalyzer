import type { GeneEntry } from "./gene";

export interface SampleGroup {
  id: string;
  group_label: string;
  group_index: number;
  sample_names: string[];
}

export interface Analysis {
  id: string;
  name: string;
  status: "processing" | "ready" | "error";
  error_message?: string | null;
  /** Resolved Ensembl gene entries selected during analysis creation. */
  mutated_genes: GeneEntry[];
  created_at: string;
  updated_at: string;
  sample_groups: SampleGroup[];
}

export interface AnalysisListItem {
  id: string;
  name: string;
  status: "processing" | "ready" | "error";
  /** Resolved Ensembl gene entries. */
  mutated_genes: GeneEntry[];
  created_at: string;
  updated_at: string;
}

export interface UploadResponse {
  analysis_id: string;
  status: string;
  event_count: number;
}
