/**
 * Shared types for the Top-10 annotated cards view.
 */

/**
 * The active display mode selected via the sidebar.
 *
 * - gene         → Genomic location (ENSG, coordinates, Ensembl link)
 * - go           → Gene Ontology terms (BP / MF / CC)
 * - panelapp     → PanelApp Australia disease panels (green/amber/red)
 * - scores       → Detailed rMATS statistics + read counts
 * - stringdb     → STRING-DB interaction network with the mutated gene
 *                  (only shown when mutated genes were defined for the analysis)
 */
export type ViewMode = "gene" | "go" | "panelapp" | "scores" | "stringdb";
