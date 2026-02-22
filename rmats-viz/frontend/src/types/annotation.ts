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

// ---------------------------------------------------------------------------
// STRING-DB interaction types
// ---------------------------------------------------------------------------

/** Metadata for a single STRING evidence channel. */
export interface ChannelMeta {
  key: string;
  /** Human-readable label (French), e.g. "Expérimental" */
  label: string;
  /** Hex colour matching STRING visual convention */
  color: string;
}

/** A publication returned by Europe PMC linked to a STRING interaction. */
export interface PMIDEntry {
  pmid: string;
  title: string;
  year: string;
  authors: string;
}

/**
 * STRING-DB interaction result returned by
 * GET /api/v1/annotations/interactions?gene_a=&gene_b=
 */
export interface GeneInteraction {
  has_interaction: boolean;
  gene_a: string;
  gene_b: string;
  /** Combined STRING score (0.0 – 1.0) */
  combined_score: number;
  /** Active evidence channels only (score > 0), keyed by channel name */
  channels: Record<string, number>;
  /** Ordered metadata for active channels */
  channel_meta: ChannelMeta[];
  /** Europe PMC publications (only populated when tscore > 0) */
  pmids: PMIDEntry[];
  /** Link to STRING-DB network page for this pair */
  string_url: string;
}
