/**
 * API module – public entry point
 * =================================
 * Re-exports all API functions from the individual modules.
 *
 * Module structure:
 *   lib/api/
 *   ├── client.ts     Shared fetchJSON helper and BASE URL constant
 *   ├── analyses.ts   Analysis CRUD (create, list, get, delete)
 *   ├── events.ts       Splicing events (list with filters, Manhattan)
 *   ├── genes.ts        Ensembl gene search and lookup
 *   ├── annotations.ts  Gene annotation (PanelApp + GO + UniProt)
 *   ├── deep-analyses.ts Deep analysis CRUD and pattern comparison
 *   └── index.ts        This file – re-exports everything
 *
 * Usage:
 *   import { listAnalyses, searchGenes } from "@/lib/api";
 */

export * from "./analyses";
export * from "./annotations";
export * from "./events";
export * from "./genes";
export * from "./splice";
export * from "./deep-analyses";
export { fetchJSON, BASE } from "./client";
