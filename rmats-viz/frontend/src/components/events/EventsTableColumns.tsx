import { createColumnHelper } from "@tanstack/react-table";
import type { SplicingEvent } from "@/types/event";
import { EventTypeBadge } from "./EventTypeBadge";
import { formatFDR, formatDeltaPSI } from "@/lib/utils";

const helper = createColumnHelper<SplicingEvent>();

export function makeEventsColumns(group1Label: string, group2Label: string) {
  return [
    helper.accessor("top_rank", {
      header: "#",
      cell: (info) => info.getValue() ?? "",
      size: 40,
    }),
    helper.accessor("event_type", {
      header: "Type",
      cell: (info) => <EventTypeBadge type={info.getValue()} />,
      size: 70,
    }),
    helper.accessor("gene_symbol", {
      header: "Gène",
      cell: (info) => <span className="font-medium">{info.getValue() ?? "—"}</span>,
    }),
    helper.accessor("chr", {
      header: "Chr",
      cell: (info) => info.getValue() ?? "—",
      size: 70,
    }),
    helper.accessor("strand", {
      header: "Brin",
      cell: (info) => info.getValue() ?? "—",
      size: 50,
    }),
    helper.accessor("exon_start", {
      header: "Exon start",
      cell: (info) => info.getValue()?.toLocaleString() ?? "—",
    }),
    helper.accessor("exon_end", {
      header: "Exon end",
      cell: (info) => info.getValue()?.toLocaleString() ?? "—",
    }),
    helper.accessor("fdr", {
      header: "FDR",
      cell: (info) => formatFDR(info.getValue()),
    }),
    helper.accessor("inc_level_difference", {
      header: "ΔPSI",
      cell: (info) => {
        const val = info.getValue();
        if (val === null || val === undefined)
          return <span className="text-gray-400">N/A</span>;
        const txt = formatDeltaPSI(val);
        const cls =
          val > 0
            ? "text-red-600 font-medium"
            : val < 0
            ? "text-blue-600 font-medium"
            : "text-gray-600";
        return <span className={cls}>{txt}</span>;
      },
    }),
    helper.display({
      id: "direction",
      header: "Direction",
      cell: ({ row }) => {
        const val = row.original.inc_level_difference;
        if (val === null || val === undefined || val === 0)
          return <span className="text-gray-300">—</span>;
        if (val > 0)
          return (
            <span className="inline-flex items-center gap-0.5 text-xs font-medium text-red-700 bg-red-50 border border-red-200 px-1.5 py-0.5 rounded whitespace-nowrap">
              ↑ {group1Label}
            </span>
          );
        return (
          <span className="inline-flex items-center gap-0.5 text-xs font-medium text-blue-700 bg-blue-50 border border-blue-200 px-1.5 py-0.5 rounded whitespace-nowrap">
            ↑ {group2Label}
          </span>
        );
      },
    }),
    helper.accessor("abs_inc_level_diff", {
      header: "|ΔPSI|",
      cell: (info) => info.getValue()?.toFixed(3) ?? "—",
    }),
    helper.accessor("inc_level_1", {
      header: "IncLevel1",
      cell: (info) => (
        <span className="text-xs text-gray-500 truncate max-w-[120px] block">
          {info.getValue() ?? "—"}
        </span>
      ),
    }),
    helper.accessor("inc_level_2", {
      header: "IncLevel2",
      cell: (info) => (
        <span className="text-xs text-gray-500 truncate max-w-[120px] block">
          {info.getValue() ?? "—"}
        </span>
      ),
    }),
  ];
}
