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
  created_at: string;
  updated_at: string;
  sample_groups: SampleGroup[];
}

export interface AnalysisListItem {
  id: string;
  name: string;
  status: "processing" | "ready" | "error";
  created_at: string;
  updated_at: string;
}

export interface UploadResponse {
  analysis_id: string;
  status: string;
  event_count: number;
}
