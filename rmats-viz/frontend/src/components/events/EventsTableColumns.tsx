import { createColumnHelper } from "@tanstack/react-table";
import type { SplicingEvent } from "@/types/event";
import { EventTypeBadge } from "./EventTypeBadge";
import { formatFDR, formatDeltaPSI } from "@/lib/utils";

const helper = createColumnHelper<SplicingEvent>();

export const eventsColumns = [
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
    cell: (info) => formatDeltaPSI(info.getValue()),
  }),
  helper.accessor("abs_inc_level_diff", {
    header: "|ΔPSI|",
    cell: (info) => info.getValue()?.toFixed(3) ?? "—",
  }),
  helper.accessor("inc_level_1", {
    header: "IncLevel1",
    cell: (info) => <span className="text-xs text-gray-500 truncate max-w-[120px] block">{info.getValue() ?? "—"}</span>,
  }),
  helper.accessor("inc_level_2", {
    header: "IncLevel2",
    cell: (info) => <span className="text-xs text-gray-500 truncate max-w-[120px] block">{info.getValue() ?? "—"}</span>,
  }),
];
