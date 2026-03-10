import { createColumnHelper } from "@tanstack/react-table";
import type { SplicingEvent } from "@/types/event";
import { EventTypeBadge } from "./EventTypeBadge";
import { formatFDR, formatDeltaPSI } from "@/lib/utils";

const helper = createColumnHelper<SplicingEvent>();

/**
 * Accepts a `t` translation function so column headers are reactive to language changes.
 */
export function makeEventsColumns(
  group1Label: string,
  group2Label: string,
  showIncLevel = false,
  t: (key: string, vars?: Record<string, string | number>) => string = (k) => k,
) {
  const baseColumns = [
    helper.accessor("event_type", {
      header: t("eventTable.type"),
      cell: (info) => <EventTypeBadge type={info.getValue()} />,
      size: 70,
    }),
    helper.accessor("gene_symbol", {
      header: t("eventTable.gene"),
      cell: (info) => (
        <span className="font-semibold text-foreground">{info.getValue() ?? "—"}</span>
      ),
    }),
    helper.accessor("chr", {
      header: t("eventTable.chr"),
      cell: (info) => <span className="text-muted-foreground">{info.getValue() ?? "—"}</span>,
      size: 70,
    }),
    helper.accessor("strand", {
      header: t("eventTable.strand"),
      cell: (info) => <span className="text-muted-foreground">{info.getValue() ?? "—"}</span>,
      size: 50,
    }),
    helper.accessor("exon_start", {
      header: t("eventTable.exonStart"),
      cell: (info) => (
        <span className="text-muted-foreground tabular-nums">
          {info.getValue()?.toLocaleString() ?? "—"}
        </span>
      ),
    }),
    helper.accessor("exon_end", {
      header: t("eventTable.exonEnd"),
      cell: (info) => (
        <span className="text-muted-foreground tabular-nums">
          {info.getValue()?.toLocaleString() ?? "—"}
        </span>
      ),
    }),
    helper.accessor("fdr", {
      header: t("eventTable.fdr"),
      cell: (info) => (
        <span className="tabular-nums font-medium">{formatFDR(info.getValue())}</span>
      ),
    }),
    helper.accessor("inc_level_difference", {
      header: t("eventTable.deltaPsi"),
      cell: (info) => {
        const val = info.getValue();
        if (val === null || val === undefined)
          return <span className="text-muted-foreground">N/A</span>;
        const txt = formatDeltaPSI(val);
        const cls =
          val > 0
            ? "text-red-600 dark:text-red-400 font-semibold"
            : val < 0
            ? "text-blue-600 dark:text-blue-400 font-semibold"
            : "text-muted-foreground";
        return <span className={`tabular-nums ${cls}`}>{txt}</span>;
      },
    }),
    helper.display({
      id: "direction",
      header: t("eventTable.direction"),
      cell: ({ row }) => {
        const val = row.original.inc_level_difference;
        const isSE = row.original.event_type === "SE";
        if (val === null || val === undefined || val === 0)
          return <span className="text-muted-foreground/30">—</span>;
        if (isSE) {
          // ΔΨ < 0 → more skipping in group1; ΔΨ > 0 → more skipping in group2
          const moreSkippingLabel = val < 0 ? group1Label : group2Label;
          const seColor = val > 0
            ? "text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-950/40 border-red-200 dark:border-red-800"
            : "text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-950/40 border-blue-200 dark:border-blue-800";
          return (
            <span className={`inline-flex items-center gap-0.5 text-xs font-medium border ${seColor} px-1.5 py-0.5 rounded whitespace-nowrap`}>
              {t("annotatedCard.direction.skippingUp", { group: moreSkippingLabel })}
            </span>
          );
        }
        // Non-SE: simple inclusion direction
        if (val > 0)
          return (
            <span className="inline-flex items-center gap-0.5 text-xs font-medium text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 px-1.5 py-0.5 rounded whitespace-nowrap">
              ↑ {group1Label}
            </span>
          );
        return (
          <span className="inline-flex items-center gap-0.5 text-xs font-medium text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800 px-1.5 py-0.5 rounded whitespace-nowrap">
            ↑ {group2Label}
          </span>
        );
      },
    }),
    helper.accessor("abs_inc_level_diff", {
      header: t("eventTable.absDeltaPsi"),
      cell: (info) => (
        <span className="tabular-nums font-medium">
          {info.getValue()?.toFixed(3) ?? "—"}
        </span>
      ),
    }),
  ];

  const incLevelColumns = showIncLevel
    ? [
        helper.accessor("inc_level_1", {
          header: t("eventTable.incLevel1"),
          cell: (info) => (
            <span className="text-xs text-muted-foreground truncate max-w-[120px] block tabular-nums">
              {info.getValue() ?? "—"}
            </span>
          ),
        }),
        helper.accessor("inc_level_2", {
          header: t("eventTable.incLevel2"),
          cell: (info) => (
            <span className="text-xs text-muted-foreground truncate max-w-[120px] block tabular-nums">
              {info.getValue() ?? "—"}
            </span>
          ),
        }),
      ]
    : [];

  return [...baseColumns, ...incLevelColumns];
}
