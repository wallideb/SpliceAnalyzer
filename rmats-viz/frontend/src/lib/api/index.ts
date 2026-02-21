/**
 * API module – public entry point
 * =================================
 * Re-exports all API functions from the individual modules.
 *
 * Module structure:
 *   lib/api/
 *   ├── client.ts     Shared fetchJSON helper and BASE URL constant
 *   ├── analyses.ts   Analysis CRUD (create, list, get, delete)
 *   ├── events.ts     Splicing events (list with filters, top-10)
 *   ├── genes.ts      Ensembl gene search and lookup
 *   └── index.ts      This file – re-exports everything
 *
 * Usage:
 *   import { listAnalyses, searchGenes } from "@/lib/api";
 */

export * from "./analyses";
export * from "./events";
export * from "./genes";
export { fetchJSON, BASE } from "./client";
