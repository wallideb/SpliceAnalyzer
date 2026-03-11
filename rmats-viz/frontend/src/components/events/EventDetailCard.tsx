"use client";

/**
 * EventDetailCard
 * ================
 * Floating detail card shown when clicking a data point on the Manhattan plot.
 * Displays key event info and provides a "View in table" action.
 */

import { useT } from "@/contexts/LanguageContext";
import type { ManhattanPoint } from "./ManhattanPlot";

interface Props {
  event: ManhattanPoint;
  /** Pixel position relative to the plot container for anchoring the card. */
  anchor: { x: number; y: number };
  onClose: () => void;
  /** Navigate to event in table (filter by gene, scroll). */
  onViewInTable?: (event: ManhattanPoint) => void;
}

const TYPE_COLORS: Record<string, string> = {
  SE: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300 border-blue-200 dark:border-blue-700",
  RI: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300 border-amber-200 dark:border-amber-700",
  A3SS: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300 border-emerald-200 dark:border-emerald-700",
  A5SS: "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300 border-violet-200 dark:border-violet-700",
  MXE: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300 border-red-200 dark:border-red-700",
};

export function EventDetailCard({ event, anchor, onClose, onViewInTable }: Props) {
  const t = useT();

  const dpsi = event.inc_level_difference;
  const dpsiColor = dpsi == null ? "" : dpsi > 0 ? "text-blue-600 dark:text-blue-400" : "text-red-600 dark:text-red-400";
  const isSignificant = event.fdr != null && event.fdr < 0.05;

  return (
    <div
      className="absolute z-20 bg-popover border border-border rounded-xl shadow-xl p-3 w-64 space-y-2 animate-in fade-in zoom-in-95 duration-150"
      style={{
        left: Math.min(anchor.x, 636),  // Keep within 900px SVG width
        top: anchor.y + 8,
      }}
    >
      {/* Close button */}
      <button
        onClick={onClose}
        className="absolute top-2 right-2 w-5 h-5 flex items-center justify-center rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
        aria-label="Close"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>

      {/* Gene + type */}
      <div className="flex items-center gap-2 pr-5">
        <span className="text-sm font-bold text-foreground truncate">
          {event.gene_symbol ?? "Unknown"}
        </span>
        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${TYPE_COLORS[event.event_type] ?? "bg-muted text-muted-foreground border-border"}`}>
          {event.event_type}
        </span>
      </div>

      {/* Coordinates */}
      <p className="text-xs text-muted-foreground font-mono">
        chr{event.chr?.replace(/^chr/i, "")}:{event.position?.toLocaleString()}
      </p>

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <span className="text-muted-foreground">FDR</span>
        <span className={`font-semibold tabular-nums text-right ${isSignificant ? "text-green-600 dark:text-green-400" : "text-foreground"}`}>
          {event.fdr != null ? event.fdr.toExponential(2) : "—"}
        </span>
        <span className="text-muted-foreground">ΔPSI</span>
        <span className={`font-semibold tabular-nums text-right ${dpsiColor}`}>
          {dpsi != null ? (dpsi >= 0 ? `+${dpsi.toFixed(3)}` : dpsi.toFixed(3)) : "—"}
        </span>
      </div>

      {/* Significance badge */}
      {isSignificant && (
        <div className="flex items-center gap-1.5">
          <span className="inline-block w-2 h-2 rounded-full bg-green-500" />
          <span className="text-[10px] font-semibold text-green-600 dark:text-green-400">
            Significant (FDR &lt; 0.05)
          </span>
        </div>
      )}

      {/* Action */}
      {onViewInTable && (
        <button
          onClick={() => onViewInTable(event)}
          className="w-full text-xs font-semibold text-center py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white transition-colors"
        >
          {t("manhattan.viewInTable")}
        </button>
      )}
    </div>
  );
}
