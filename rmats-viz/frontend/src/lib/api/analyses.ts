/**
 * Analyses API module
 * ====================
 * Functions for creating, listing, fetching, and deleting analyses.
 *
 * Endpoints used:
 *   POST   /api/v1/analyses/uploads                – Open a chunked-upload session
 *   PUT    /api/v1/analyses/uploads/{uid}/chunk    – Append one ≤ 512 KB chunk of a file
 *   POST   /api/v1/analyses/uploads/{uid}/finalize – Assemble the files, create the analysis
 *   DELETE /api/v1/analyses/uploads/{uid}          – Abort a session (best effort)
 *   GET    /api/v1/analyses          – List all analyses
 *   GET    /api/v1/analyses/{id}     – Get analysis details
 *   DELETE /api/v1/analyses/{id}     – Delete an analysis
 *
 * The single-shot `POST /api/v1/analyses` (whole files in one multipart body)
 * is kept for curl / API clients but is NOT used by the browser: reverse
 * proxies such as the GitHub Codespaces port forwarder or a default nginx
 * reject bodies above ~1 MB with HTTP 413, and rMATS files are 10–100 MB.
 *
 * Note: Excel export is only available for deep analyses (not the general analysis).
 */

import type { Analysis, AnalysisListItem, UploadResponse } from "@/types/analysis";
import type { GeneEntry } from "@/types/gene";
import { BASE, fetchJSON, type ApiError } from "./client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UploadPayload {
  name: string;
  group1_label: string;
  group2_label: string;
  group1_samples: string[];
  group2_samples: string[];
  /** Resolved gene entries (symbol + Ensembl ID) selected via autocomplete. */
  mutated_genes: GeneEntry[];
  files: File[];
}

/** Progress of `uploadAnalysis`: bytes sent so far, then the server-side import. */
export interface UploadProgress {
  phase: "upload" | "processing";
  sentBytes: number;
  totalBytes: number;
  /** Original (display) name of the file currently being sent. */
  file?: string;
}

/** Size of one chunk request; must stay below the ~1 MB body cap of common proxies. */
export const CHUNK_SIZE = 512 * 1024;
/** A failed chunk PUT is retried this many times (the server is idempotent on the last chunk). */
const CHUNK_RETRIES = 3;

/**
 * Mirror of the backend's filename rule (basename, `[A-Za-z0-9._-]` only):
 * disallowed characters become `_` so the server never answers 422.  The
 * original `File.name` is kept for the UI only.
 */
export function safeUploadFilename(name: string): string {
  const base = name.split(/[\\/]/).pop() ?? "";
  const cleaned = base.replace(/[^A-Za-z0-9._-]/g, "_");
  return cleaned === "" || cleaned === "." || cleaned === ".." ? `file_${cleaned.length}` : cleaned;
}

/**
 * Give every file a unique server-side name: two distinct browser files may
 * collapse onto the same sanitised name (e.g. "SE MATS.txt" and "SE_MATS.txt").
 */
function uniqueUploadNames(files: File[]): string[] {
  const seen = new Set<string>();
  return files.map((f) => {
    let name = safeUploadFilename(f.name);
    if (seen.has(name)) {
      const dot = name.lastIndexOf(".");
      const stem = dot > 0 ? name.slice(0, dot) : name;
      const ext = dot > 0 ? name.slice(dot) : "";
      let n = 2;
      while (seen.has(`${stem}_${n}${ext}`)) n += 1;
      name = `${stem}_${n}${ext}`;
    }
    seen.add(name);
    return name;
  });
}

// ---------------------------------------------------------------------------
// Functions
// ---------------------------------------------------------------------------

export async function listAnalyses(): Promise<AnalysisListItem[]> {
  return fetchJSON(`${BASE}/analyses`);
}

export async function getAnalysis(id: string): Promise<Analysis> {
  return fetchJSON(`${BASE}/analyses/${id}`);
}

// DELETE goes through the Next.js rewrite proxy like every other call (C11);
// the long-running cascade delete is covered by `experimental.proxyTimeout`
// in next.config.mjs (10 min).
export async function deleteAnalysis(id: string): Promise<void> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10 * 60 * 1000); // 10 min
  try {
    const resp = await fetch(`${BASE}/analyses/${id}`, {
      method: "DELETE",
      signal: controller.signal,
    });
    if (!resp.ok) throw new Error(`Delete failed: ${resp.status}`);
  } finally {
    clearTimeout(timeout);
  }
}

export async function downloadDeepAnalysisExcel(
  analysisId: string,
  deepAnalysisId: string,
  include: string[] = ["core"],
): Promise<void> {
  const includeParam = include.join(",");
  const url = `${BASE}/export/${analysisId}/deep-analysis/${deepAnalysisId}/excel?include=${encodeURIComponent(includeParam)}`;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error("Export failed");
  const blob = await resp.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `rmats_deep_${deepAnalysisId}.xlsx`;
  a.click();
  URL.revokeObjectURL(a.href);
}

export async function downloadAnalysisPDF(
  analysisId: string,
  deepAnalysisId?: string,
  sections?: string[],
): Promise<void> {
  let url = deepAnalysisId
    ? `${BASE}/export/${analysisId}/deep-analysis/${deepAnalysisId}/pdf`
    : `${BASE}/export/${analysisId}/pdf`;
  if (sections && sections.length > 0) {
    url += `?sections=${encodeURIComponent(sections.join(","))}`;
  }
  const resp = await fetch(url);
  if (!resp.ok) {
    if (resp.status === 409) {
      const body = await resp.json().catch(() => null);
      const err = new Error(body?.detail ?? "Splice feature computation is still in progress.");
      (err as ApiError).status = 409;
      throw err;
    }
    throw new Error("PDF export failed");
  }
  const blob = await resp.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = deepAnalysisId ? `rmats_deep_${deepAnalysisId}.pdf` : `rmats_${analysisId}.pdf`;
  a.click();
  URL.revokeObjectURL(a.href);
}

const RETRYABLE_STATUS = new Set([408, 409, 429]);

async function putChunk(uploadId: string, filename: string, index: number, total: number, chunk: Blob): Promise<void> {
  const url =
    `${BASE}/analyses/uploads/${uploadId}/chunk?filename=${encodeURIComponent(filename)}` +
    `&index=${index}&total=${total}`;
  let lastError: Error = new Error("Chunk upload failed");
  for (let attempt = 0; attempt <= CHUNK_RETRIES; attempt++) {
    try {
      const resp = await fetch(url, {
        method: "PUT",
        body: chunk,
        headers: { "Content-Type": "application/octet-stream" },
      });
      if (resp.ok) return;
      const text = await resp.text().catch(() => resp.statusText);
      const err: ApiError = new Error(`Chunk upload failed (${resp.status}): ${text}`);
      err.status = resp.status;
      // A definitive client error (404 session gone, 413, 422 …) will not
      // succeed on retry; 408/409/429 and every 5xx are worth another try.
      if (resp.status >= 400 && resp.status < 500 && !RETRYABLE_STATUS.has(resp.status)) throw err;
      lastError = err;
    } catch (e) {
      if ((e as ApiError).status !== undefined) throw e; // the definitive error above
      lastError = e instanceof Error ? e : new Error(String(e)); // network failure → retry
    }
    if (attempt < CHUNK_RETRIES) await new Promise((r) => setTimeout(r, 500 * (attempt + 1)));
  }
  throw lastError;
}

/**
 * Create an analysis through the chunked-upload path.
 *
 * 1. `POST /analyses/uploads` opens a session.
 * 2. Each file is sliced into `CHUNK_SIZE` pieces which are PUT sequentially
 *    (`index` must follow the number of chunks the server already holds; a
 *    resend of the last chunk is acknowledged without appending, so retries
 *    after a lost response are safe).  `onProgress` fires after every chunk.
 * 3. `POST …/finalize` sends the same form fields as `POST /analyses` plus the
 *    JSON list of filenames; the server assembles the files and imports them.
 *
 * Any failure after the session was opened aborts it with a best-effort
 * `DELETE …/uploads/{id}` before the error is re-thrown.
 */
export async function uploadAnalysis(
  payload: UploadPayload,
  onProgress?: (p: UploadProgress) => void,
): Promise<UploadResponse> {
  const totalBytes = payload.files.reduce((n, f) => n + f.size, 0);
  const serverNames = uniqueUploadNames(payload.files);

  const session = await fetchJSON<{ upload_id: string }>(`${BASE}/analyses/uploads`, { method: "POST" });
  const uploadId = session.upload_id;

  try {
    let sentBytes = 0;
    onProgress?.({ phase: "upload", sentBytes, totalBytes, file: payload.files[0]?.name });
    for (let fi = 0; fi < payload.files.length; fi++) {
      const file = payload.files[fi];
      const serverName = serverNames[fi];
      // An empty file is still one (zero-byte) chunk so the server records it.
      const total = Math.max(1, Math.ceil(file.size / CHUNK_SIZE));
      for (let index = 0; index < total; index++) {
        const chunk = file.slice(index * CHUNK_SIZE, Math.min(file.size, (index + 1) * CHUNK_SIZE));
        await putChunk(uploadId, serverName, index, total, chunk);
        sentBytes += chunk.size;
        onProgress?.({ phase: "upload", sentBytes, totalBytes, file: file.name });
      }
    }

    onProgress?.({ phase: "processing", sentBytes: totalBytes, totalBytes });
    const form = new FormData();
    form.append("name", payload.name);
    form.append("group1_label", payload.group1_label);
    form.append("group2_label", payload.group2_label);
    form.append("group1_samples", JSON.stringify(payload.group1_samples));
    form.append("group2_samples", JSON.stringify(payload.group2_samples));
    // Genes are stored as JSON objects: [{"symbol":"BRCA1","ensembl_id":"ENSG…","display":"…"}]
    form.append("mutated_genes", JSON.stringify(payload.mutated_genes));
    form.append("files", JSON.stringify(serverNames));
    // Parsing and storing 200 MB+ of events can take several minutes.
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10 * 60 * 1000); // 10 min
    try {
      return await fetchJSON<UploadResponse>(`${BASE}/analyses/uploads/${uploadId}/finalize`, {
        method: "POST",
        body: form,
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timeout);
    }
  } catch (e) {
    // finalize removes the session itself (success or failure); for every
    // other failure make sure no partial files linger on the server.
    await fetch(`${BASE}/analyses/uploads/${uploadId}`, { method: "DELETE" }).catch(() => undefined);
    throw e;
  }
}
