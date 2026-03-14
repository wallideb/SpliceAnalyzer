/**
 * Next.js App Router handler — single-analysis operations
 * =========================================================
 * Proxies GET and DELETE to the FastAPI backend using a direct
 * server-to-server fetch (frontend container → backend container).
 * This file is intentionally kept alongside the /api/* rewrite in
 * next.config.mjs: the rewrite (beforeFiles) takes precedence in the
 * current container; this file acts as an always-live fallback via
 * the src/ volume mount for containers that have a stale config.
 */

import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.API_URL ?? "http://localhost:8000";

export async function GET(
  _req: NextRequest,
  { params }: { params: { id: string } },
) {
  const res = await fetch(`${BACKEND}/api/v1/analyses/${params.id}`);
  const body = await res.text();
  return new NextResponse(body, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("Content-Type") ?? "application/json" },
  });
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: { id: string } },
) {
  // Batched cascade deletion of large analyses can take several minutes.
  // No AbortController here — Next.js experimental.proxyTimeout (10 min)
  // and uvicorn --timeout-keep-alive (600 s) govern the upper bound.
  const res = await fetch(`${BACKEND}/api/v1/analyses/${params.id}`, {
    method: "DELETE",
  });
  return new NextResponse(null, { status: res.status });
}
