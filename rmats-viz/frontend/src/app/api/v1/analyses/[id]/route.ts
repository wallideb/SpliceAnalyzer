import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.API_URL || "http://localhost:8000";

export async function DELETE(
  _req: NextRequest,
  { params }: { params: { id: string } },
) {
  const res = await fetch(`${API_URL}/api/v1/analyses/${params.id}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    return NextResponse.json({ error: text }, { status: res.status });
  }
  return new NextResponse(null, { status: 204 });
}
