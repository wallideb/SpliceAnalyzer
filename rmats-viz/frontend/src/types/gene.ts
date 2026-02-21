/**
 * Gene types
 * ===========
 * TypeScript interfaces for Ensembl gene entries used in autocomplete
 * and stored in analyses.
 */

/** A resolved gene entry with its Ensembl stable identifier. */
export interface GeneEntry {
  /** HUGO gene symbol, e.g. "BRCA1" */
  symbol: string;
  /** Ensembl stable gene ID, e.g. "ENSG00000012048" */
  ensembl_id: string;
  /** Human-readable label: "BRCA1 (ENSG00000012048)" */
  display: string;
}

/** Response from GET /api/v1/genes/search */
export interface GeneSearchResponse {
  query: string;
  results: GeneEntry[];
  total: number;
}
