/**
 * Annotations API module
 * =======================
 * Fetches gene annotations aggregated from PanelApp Australia, GO, UniProt,
 * and STRING-DB protein interactions.
 *
 * Endpoints used (backend proxy):
 *   GET /api/v1/annotations/gene/{symbol}?ensembl_id={ensg}
 *   GET /api/v1/annotations/interactions?gene_a={A}&gene_b={B}&species={taxid}
 *
 * The backend runs PanelApp, mygene.info (GO) and UniProt requests in parallel.
 * STRING-DB queries are also proxied through the backend (no browser CORS issues).
 */

import type { GeneAnnotation, GeneInteraction } from "@/types/annotation";
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

/**
 * Fetch STRING-DB interaction data between two genes.
 *
 * The backend queries STRING /network and, when text-mining evidence is
 * present, also fetches co-mentioning PMIDs from Europe PMC.
 *
 * @param geneA    First HUGO gene symbol (e.g. the mutated gene)
 * @param geneB    Second HUGO gene symbol (e.g. the event gene)
 * @param species  NCBI taxonomy ID (default 9606 = Homo sapiens)
 */
export async function getGeneInteractions(
  geneA: string,
  geneB: string,
  species = 9606,
): Promise<GeneInteraction> {
  const params = new URLSearchParams({
    gene_a: geneA,
    gene_b: geneB,
    species: String(species),
  });
  return fetchJSON<GeneInteraction>(`${BASE}/annotations/interactions?${params}`);
}
