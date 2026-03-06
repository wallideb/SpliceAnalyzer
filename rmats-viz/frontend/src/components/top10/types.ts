/**
 * Shared types for the Top-10 annotated cards view.
 */

/**
 * The active display mode selected via the sidebar.
 *
 * Base modes (always available in Top-10 and deep-analysis):
 * - gene         → Genomic location (ENSG, coordinates, Ensembl link)
 * - go           → Gene Ontology terms (BP / MF / CC)
 * - scores       → Detailed rMATS statistics + read counts
 * - stringdb     → STRING-DB interaction network with the mutated gene
 *                  (only shown when mutated genes were defined for the analysis)
 *
 * Note: PanelApp confidence is now shown as a colored badge directly on each
 * card (green / amber / red) with panel names revealed on hover — no longer a
 * dedicated sidebar tab.
 *
 * Extended modes (deep-analysis only):
 * - pathways     → Molecular pathway enrichment (KEGG / Reactome)
 * - motifs       → Recurrent splicing motifs across SE events
 * - splice       → Splice-site consensus strength (5'/3'/branch/PPT)
 */
export type ViewMode =
  | "gene"
  | "go"
  | "scores"
  | "stringdb"
  | "pathways"
  | "motifs"
  | "splice";
