/**
 * API client – shared HTTP helper
 * ================================
 * A thin wrapper around `fetch` that handles JSON parsing and error
 * propagation. All API modules import from this file.
 */

const BASE = "/api/v1";

export { BASE };

/** Error thrown by `fetchJSON` — carries the HTTP status code (C10). */
export interface ApiError extends Error {
  status?: number;
}

export async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, options);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    const err: ApiError = new Error(`API error ${res.status}: ${text}`);
    err.status = res.status;
    throw err;
  }
  return res.json() as Promise<T>;
}
