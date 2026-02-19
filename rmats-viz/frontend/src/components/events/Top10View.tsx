import type { SplicingEvent } from "@/types/event";
import { EventTypeBadge } from "./EventTypeBadge";
import { formatFDR, formatDeltaPSI, formatCoord } from "@/lib/utils";

export function Top10View({ events }: { events: SplicingEvent[] }) {
  if (events.length === 0) {
    return <p className="text-gray-400 text-sm">Aucun événement top-10 trouvé.</p>;
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      {events.map((ev) => (
        <div
          key={ev.id}
          className="border rounded-lg p-4 bg-white shadow-sm space-y-3 hover:shadow-md transition-shadow"
        >
          {/* Header */}
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="w-7 h-7 flex items-center justify-center rounded-full bg-blue-600 text-white text-xs font-bold shrink-0">
                {ev.top_rank}
              </span>
              <span className="font-bold text-base">{ev.gene_symbol ?? ev.gene_id ?? "—"}</span>
            </div>
            <EventTypeBadge type={ev.event_type} />
          </div>

          {/* Stats */}
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
            <Stat label="FDR" value={formatFDR(ev.fdr)} highlight />
            <Stat label="ΔPSI" value={formatDeltaPSI(ev.inc_level_difference)} highlight />
            <Stat label="|ΔPSI|" value={ev.abs_inc_level_diff?.toFixed(3) ?? "—"} />
            <Stat label="Brin" value={`${ev.chr ?? "?"} ${ev.strand ?? ""}`} />
          </div>

          {/* Coordinates */}
          <div className="text-xs text-gray-500 bg-gray-50 rounded px-3 py-2 space-y-0.5">
            <div>
              <span className="font-medium text-gray-600">Exon:</span>{" "}
              {formatCoord(ev.exon_start)} – {formatCoord(ev.exon_end)}
            </div>
            <div>
              <span className="font-medium text-gray-600">Upstream:</span>{" "}
              {formatCoord(ev.upstream_es)} – {formatCoord(ev.upstream_ee)}
            </div>
            <div>
              <span className="font-medium text-gray-600">Downstream:</span>{" "}
              {formatCoord(ev.downstream_es)} – {formatCoord(ev.downstream_ee)}
            </div>
          </div>

          {/* Read counts (abbreviated) */}
          {ev.ijc_sample_1 && (
            <div className="text-xs text-gray-400">
              <span className="font-medium text-gray-500">IJC s1:</span>{" "}
              {ev.ijc_sample_1.split(",").slice(0, 3).join(", ")}
              {ev.ijc_sample_1.split(",").length > 3 ? "…" : ""}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function Stat({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div>
      <dt className="text-xs text-gray-400">{label}</dt>
      <dd className={`font-semibold ${highlight ? "text-gray-900" : "text-gray-600"}`}>{value}</dd>
    </div>
  );
}
