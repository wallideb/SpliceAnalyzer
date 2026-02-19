import type { EventType } from "@/types/event";

const COLORS: Record<EventType, string> = {
  SE: "bg-blue-100 text-blue-700",
  RI: "bg-amber-100 text-amber-700",
  A3SS: "bg-green-100 text-green-700",
  A5SS: "bg-purple-100 text-purple-700",
  MXE: "bg-rose-100 text-rose-700",
};

export function EventTypeBadge({ type }: { type: string }) {
  const color = COLORS[type as EventType] ?? "bg-gray-100 text-gray-700";
  return (
    <span className={`inline-block text-xs font-semibold px-2 py-0.5 rounded-full ${color}`}>
      {type}
    </span>
  );
}
