/**
 * Analyses API module
 * ====================
 * Functions for creating, listing, fetching, and deleting analyses.
 *
 * Endpoints used:
 *   POST   /api/v1/analyses          – Create a new analysis (multipart/form-data)
 *   GET    /api/v1/analyses          – List all analyses
 *   GET    /api/v1/analyses/{id}     – Get analysis details
 *   DELETE /api/v1/analyses/{id}     – Delete an analysis
 */

import type { Analysis, AnalysisListItem, UploadResponse } from "@/types/analysis";
import type { GeneEntry } from "@/types/gene";
import { BASE, fetchJSON } from "./client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UploadPayload {
  name: string;
  group1_label: string;
  group2_label: string;
  group1_samples: string[];
  group2_samples: string[];
  /** Resolved gene entries (symbol + Ensembl ID) selected via autocomplete. */
  mutated_genes: GeneEntry[];
  files: File[];
}

// ---------------------------------------------------------------------------
// Functions
// ---------------------------------------------------------------------------

export async function listAnalyses(): Promise<AnalysisListItem[]> {
  return fetchJSON(`${BASE}/analyses`);
}

export async function getAnalysis(id: string): Promise<Analysis> {
  return fetchJSON(`${BASE}/analyses/${id}`);
}

export async function deleteAnalysis(id: string): Promise<void> {
  const resp = await fetch(`${BASE}/analyses/${id}`, { method: "DELETE" });
  if (!resp.ok) throw new Error(`Delete failed: ${resp.status}`);
}

export async function downloadAnalysisExcel(
  analysisId: string,
  include: string[] = ["core"],
): Promise<void> {
  const includeParam = include.join(",");
  const url = `${BASE}/export/${analysisId}/excel?include=${encodeURIComponent(includeParam)}`;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error("Export failed");
  const blob = await resp.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `rmats_${analysisId}.xlsx`;
  a.click();
  URL.revokeObjectURL(a.href);
}

export async function downloadAnalysisPDF(analysisId: string): Promise<void> {
  const url = `${BASE}/export/${analysisId}/pdf`;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error("PDF export failed");
  const blob = await resp.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `rmats_${analysisId}.pdf`;
  a.click();
  URL.revokeObjectURL(a.href);
}

export async function uploadAnalysis(payload: UploadPayload): Promise<UploadResponse> {
  const form = new FormData();
  form.append("name", payload.name);
  form.append("group1_label", payload.group1_label);
  form.append("group2_label", payload.group2_label);
  form.append("group1_samples", JSON.stringify(payload.group1_samples));
  form.append("group2_samples", JSON.stringify(payload.group2_samples));
  // Genes are stored as JSON objects: [{"symbol":"BRCA1","ensembl_id":"ENSG…","display":"…"}]
  form.append("mutated_genes", JSON.stringify(payload.mutated_genes));
  for (const file of payload.files) {
    form.append("files", file);
  }
  return fetchJSON(`${BASE}/analyses`, { method: "POST", body: form });
}
