import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.API_URL || "http://localhost:8000";

export async function GET(
  _req: NextRequest,
  { params }: { params: { id: string } },
) {
  const res = await fetch(`${API_URL}/api/v1/analyses/${params.id}`);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    return NextResponse.json({ error: text }, { status: res.status });
  }
  const data = await res.json();
  return NextResponse.json(data);
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: { id: string } },
) {
  // Large analyses (thousands of events with cascade) can take minutes to delete.
  // Use AbortController with a generous timeout to avoid premature cancellation.
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5 * 60 * 1000); // 5 min
  try {
    const res = await fetch(`${API_URL}/api/v1/analyses/${params.id}`, {
      method: "DELETE",
      signal: controller.signal,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText);
      return NextResponse.json({ error: text }, { status: res.status });
    }
    return new NextResponse(null, { status: 204 });
  } catch (err) {
    if ((err as Error).name === "AbortError") {
      return NextResponse.json(
        { error: "Delete timed out — the analysis may still be deleting in the background" },
        { status: 504 },
      );
    }
    return NextResponse.json(
      { error: `Delete failed: ${(err as Error).message}` },
      { status: 502 },
    );
  } finally {
    clearTimeout(timeout);
  }
}
