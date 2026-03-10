/**
 * Events API module
 * ==================
 * Functions for fetching splicing events associated with an analysis.
 *
 * Endpoints used:
 *   GET /api/v1/analyses/{id}/events       – Paginated, filtered event list
 *   GET /api/v1/analyses/{id}/events/top10 – Top-10 ranked events
 */

import type { EventsPage, SplicingEvent } from "@/types/event";
import { BASE, fetchJSON } from "./client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface EventsQuery {
  event_type?: string;
  gene_symbol?: string;
  fdr_max?: number;
  p_value_max?: number;
  delta_psi_min?: number;
  sort_by?: "fdr" | "p_value" | "abs_inc_level_diff" | "gene_symbol";
  sort_dir?: "asc" | "desc";
  page?: number;
  page_size?: number;
  /** When true, top-10 ranked events are excluded from the result. */
  exclude_top10?: boolean;
}

// ---------------------------------------------------------------------------
// Functions
// ---------------------------------------------------------------------------

export async function listEvents(analysisId: string, query: EventsQuery = {}): Promise<EventsPage> {
  const params = new URLSearchParams();
  if (query.event_type) params.set("event_type", query.event_type);
  if (query.gene_symbol) params.set("gene_symbol", query.gene_symbol);
  if (query.fdr_max !== undefined) params.set("fdr_max", String(query.fdr_max));
  if (query.p_value_max !== undefined) params.set("p_value_max", String(query.p_value_max));
  if (query.delta_psi_min !== undefined) params.set("delta_psi_min", String(query.delta_psi_min));
  if (query.sort_by) params.set("sort_by", query.sort_by);
  if (query.sort_dir) params.set("sort_dir", query.sort_dir);
  if (query.page) params.set("page", String(query.page));
  if (query.page_size) params.set("page_size", String(query.page_size));
  if (query.exclude_top10) params.set("exclude_top10", "true");
  return fetchJSON(`${BASE}/analyses/${analysisId}/events?${params}`);
}

export async function getManhattanData(analysisId: string): Promise<import("@/components/events/ManhattanPlot").ManhattanPoint[]> {
  return fetchJSON(`${BASE}/analyses/${analysisId}/events/manhattan`);
}

export async function getTop10(analysisId: string, eventType?: string, limit?: number): Promise<SplicingEvent[]> {
  const params = new URLSearchParams();
  if (eventType) params.set("event_type", encodeURIComponent(eventType));
  if (limit !== undefined && limit !== 10) params.set("limit", String(limit));
  const qs = params.toString();
  return fetchJSON(`${BASE}/analyses/${analysisId}/events/top10${qs ? `?${qs}` : ""}`);
}
