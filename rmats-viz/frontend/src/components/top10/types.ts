/**
 * Shared types for the Top-10 annotated cards view.
 */

/**
 * The active display mode selected via the sidebar.
 *
 * Base modes (always available):
 * - gene         → Event details (gene info + rMATS scores)
 * - go           → Gene Ontology terms (BP / MF / CC)
 * - stringdb     → STRING-DB interaction network with the mutated gene
 *                  (only shown when mutated genes were defined for the analysis)
 *
 * Extended modes (deep-analysis only):
 * - pathways     → Molecular pathway enrichment (KEGG / Reactome)
 * - motifs       → Recurrent splicing motifs across SE events
 * - splice       → Splice-site consensus strength (5'/3'/branch/PPT)
 */
export type ViewMode =
  | "gene"
  | "go"
  | "stringdb"
  | "pathways"
  | "motifs"
  | "splice";
