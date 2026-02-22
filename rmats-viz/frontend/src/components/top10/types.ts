/**
 * Shared types for the Top-10 annotated cards view.
 */

/**
 * The active display mode selected via the sidebar.
 *
 * Base modes (always available in Top-10 and deep-analysis):
 * - gene         → Genomic location (ENSG, coordinates, Ensembl link)
 * - go           → Gene Ontology terms (BP / MF / CC)
 * - panelapp     → PanelApp Australia disease panels (green/amber/red)
 * - scores       → Detailed rMATS statistics + read counts
 * - stringdb     → STRING-DB interaction network with the mutated gene
 *                  (only shown when mutated genes were defined for the analysis)
 *
 * Extended modes (deep-analysis only, shown as "coming soon" stubs):
 * - pathways     → Molecular pathway enrichment (KEGG / Reactome)
 * - motifs       → Recurrent splicing motifs
 * - splice       → Splice-site consensus strength (5'/3'/branch)
 */
export type ViewMode =
  | "gene"
  | "go"
  | "panelapp"
  | "scores"
  | "stringdb"
  | "pathways"
  | "motifs"
  | "splice";
