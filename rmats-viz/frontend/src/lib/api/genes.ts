/**
 * Genes API module – Ensembl integration
 * ========================================
 * Functions for gene autocomplete and exact lookup, backed by the backend
 * proxy which queries the EBI Search and Ensembl REST APIs.
 *
 * Endpoints used (backend proxy):
 *   GET /api/v1/genes/search?q={query}&limit={n}   – Autocomplete search
 *   GET /api/v1/genes/lookup/{symbol}              – Exact symbol lookup
 *
 * The backend proxies requests to:
 *   - EBI Search REST API  (prefix/wildcard autocomplete)
 *   - Ensembl REST API     (exact lookup fallback)
 */

import type { GeneEntry, GeneSearchResponse } from "@/types/gene";
import { BASE, fetchJSON } from "./client";

// ---------------------------------------------------------------------------
// Functions
// ---------------------------------------------------------------------------

/**
 * Search genes by partial symbol for autocomplete suggestions.
 *
 * @param query   - Partial or full gene symbol, e.g. "BRCA" or "TP53"
 * @param limit   - Maximum number of results (default: 10)
 * @param species - Species identifier (default: "homo_sapiens")
 * @returns Array of gene entries with symbol, ensembl_id, and display label
 */
export async function searchGenes(
  query: string,
  limit = 10,
  species = "homo_sapiens",
): Promise<GeneEntry[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit), species });
  const response = await fetchJSON<GeneSearchResponse>(`${BASE}/genes/search?${params}`);
  return response.results;
}

