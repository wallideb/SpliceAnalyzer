/**
 * Annotations API module
 * =======================
 * Fetches gene annotations aggregated from PanelApp Australia, GO, and UniProt.
 *
 * Endpoint used (backend proxy):
 *   GET /api/v1/annotations/gene/{symbol}?ensembl_id={ensg}
 *
 * The backend runs PanelApp, mygene.info (GO) and UniProt requests in parallel.
 */

import type { GeneAnnotation } from "@/types/annotation";
import { BASE, fetchJSON } from "./client";

/**
 * Fetch combined annotations (PanelApp + GO + UniProt) for a gene.
 *
 * @param symbol     HUGO gene symbol, e.g. "BRCA1"
 * @param ensemblId  Optional Ensembl ID for more precise GO lookup
 */
export async function getGeneAnnotation(
  symbol: string,
  ensemblId?: string | null,
): Promise<GeneAnnotation> {
  const params = new URLSearchParams();
  if (ensemblId) params.set("ensembl_id", ensemblId);
  const qs = params.toString() ? `?${params}` : "";
  return fetchJSON<GeneAnnotation>(
    `${BASE}/annotations/gene/${encodeURIComponent(symbol)}${qs}`,
  );
}
