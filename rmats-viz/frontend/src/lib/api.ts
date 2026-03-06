/**
 * API entry point
 * ================
 * Re-exports everything from the modular API layer at lib/api/.
 *
 * Import from here or directly from the sub-modules:
 *   import { listAnalyses } from "@/lib/api";          // this file
 *   import { listAnalyses } from "@/lib/api/analyses"; // direct
 *
 * Health check (standalone, no sub-module):
 */

export * from "./api/index";

import { fetchJSON, BASE } from "./api/client";

export async function getHealth(): Promise<{ status: string; db: string }> {
  return fetchJSON(`${BASE}/health`);
}
