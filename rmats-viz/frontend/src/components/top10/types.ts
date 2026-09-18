/**
 * Shared types for the Top-10 annotated cards view.
 */

/**
 * The active display mode selected via the sidebar.
 *
 * Base modes (always available):
 * - gene         → Annotated events (gene info + rMATS scores + GO terms + PanelApp)
 * - stringdb     → STRING-DB interaction network with the mutated gene
 *                  (only shown when mutated genes were defined for the analysis)
 *
 * Extended modes (deep-analysis only):
 * - motifs       → Recurrent splicing motifs across SE events
 * - splice       → Splice-site consensus strength (5'/3'/branch/PPT)
 * - hnrnp        → hnRNP motif enrichment
 * - enrichr      → Enrichr pathway enrichment
 */
export type ViewMode =
  | "gene"
  | "stringdb"
  | "motifs"
  | "splice"
  | "hnrnp"
  | "enrichr";
