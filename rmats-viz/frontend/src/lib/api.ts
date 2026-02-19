import type { Analysis, AnalysisListItem, UploadResponse } from "@/types/analysis";
import type { EventsPage, SplicingEvent } from "@/types/event";

const BASE = "/api/v1";

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, options);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ── Analyses ──────────────────────────────────────────────────────────────────

export async function listAnalyses(): Promise<AnalysisListItem[]> {
  return fetchJSON(`${BASE}/analyses`);
}

export async function getAnalysis(id: string): Promise<Analysis> {
  return fetchJSON(`${BASE}/analyses/${id}`);
}

export async function deleteAnalysis(id: string): Promise<void> {
  await fetch(`${BASE}/analyses/${id}`, { method: "DELETE" });
}

export interface UploadPayload {
  name: string;
  group1_label: string;
  group2_label: string;
  group1_samples: string[];
  group2_samples: string[];
  files: File[];
}

export async function uploadAnalysis(payload: UploadPayload): Promise<UploadResponse> {
  const form = new FormData();
  form.append("name", payload.name);
  form.append("group1_label", payload.group1_label);
  form.append("group2_label", payload.group2_label);
  form.append("group1_samples", JSON.stringify(payload.group1_samples));
  form.append("group2_samples", JSON.stringify(payload.group2_samples));
  for (const file of payload.files) {
    form.append("files", file);
  }
  return fetchJSON(`${BASE}/analyses`, { method: "POST", body: form });
}

// ── Events ────────────────────────────────────────────────────────────────────

export interface EventsQuery {
  event_type?: string;
  gene_symbol?: string;
  fdr_max?: number;
  p_value_max?: number;
  sort_by?: "fdr" | "p_value" | "abs_inc_level_diff" | "gene_symbol";
  sort_dir?: "asc" | "desc";
  page?: number;
  page_size?: number;
}

export async function listEvents(analysisId: string, query: EventsQuery = {}): Promise<EventsPage> {
  const params = new URLSearchParams();
  if (query.event_type) params.set("event_type", query.event_type);
  if (query.gene_symbol) params.set("gene_symbol", query.gene_symbol);
  if (query.fdr_max !== undefined) params.set("fdr_max", String(query.fdr_max));
  if (query.p_value_max !== undefined) params.set("p_value_max", String(query.p_value_max));
  if (query.sort_by) params.set("sort_by", query.sort_by);
  if (query.sort_dir) params.set("sort_dir", query.sort_dir);
  if (query.page) params.set("page", String(query.page));
  if (query.page_size) params.set("page_size", String(query.page_size));
  return fetchJSON(`${BASE}/analyses/${analysisId}/events?${params}`);
}

export async function getTop10(analysisId: string): Promise<SplicingEvent[]> {
  return fetchJSON(`${BASE}/analyses/${analysisId}/events/top10`);
}

export async function getHealth(): Promise<{ status: string; db: string }> {
  return fetchJSON(`${BASE}/health`);
}
