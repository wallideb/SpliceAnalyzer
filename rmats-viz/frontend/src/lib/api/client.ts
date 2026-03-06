/**
 * API client – shared HTTP helper
 * ================================
 * A thin wrapper around `fetch` that handles JSON parsing and error
 * propagation. All API modules import from this file.
 */

const BASE = "/api/v1";

export { BASE };

export async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, options);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}
