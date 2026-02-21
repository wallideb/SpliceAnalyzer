/**
 * Annotation types
 * =================
 * TypeScript interfaces for gene annotation data aggregated from:
 *   - PanelApp Australia (disease panels)
 *   - Gene Ontology via mygene.info (GO terms)
 *   - UniProt (protein function)
 */

/** Confidence level colours used by PanelApp. */
export type PanelConfidence = "green" | "amber" | "red" | "unknown";

/** A PanelApp Australia disease panel entry for a gene. */
export interface PanelEntry {
  panel_name: string;
  /** 3 = green, 2 = amber, 1 = red */
  confidence_level: number;
  confidence_label: PanelConfidence;
  disorders: string[];
}

/** A single Gene Ontology term. */
export interface GOTerm {
  /** GO identifier, e.g. "GO:0000077" */
  id: string;
  term: string;
  /** "BP" | "MF" | "CC" */
  category: string;
  evidence: string;
}

/** UniProt Swiss-Prot protein function annotation. */
export interface ProteinFunction {
  accession: string;
  protein_name: string;
  function: string;
  uniprot_url: string;
}

/**
 * Combined gene annotation returned by GET /api/v1/annotations/gene/{symbol}.
 */
export interface GeneAnnotation {
  symbol: string;
  ensembl_id: string | null;
  panels: PanelEntry[];
  go_terms: GOTerm[];
  protein_function: ProteinFunction | null;
}
