"use client";
import { useState } from "react";
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  SortingState,
  getSortedRowModel,
} from "@tanstack/react-table";
import type { SplicingEvent } from "@/types/event";
import { makeEventsColumns } from "./EventsTableColumns";
import { useT } from "@/contexts/LanguageContext";

interface EventsTableProps {
  data: SplicingEvent[];
  total: number;
  page: number;
  pages: number;
  onPageChange: (p: number) => void;
  loading?: boolean;
  group1Label: string;
  group2Label: string;
  showIncLevel?: boolean;
}

export function EventsTable({
  data,
  total,
  page,
  pages,
  onPageChange,
  loading,
  group1Label,
  group2Label,
  showIncLevel = false,
}: EventsTableProps) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const t = useT();

  const columns = makeEventsColumns(group1Label, group2Label, showIncLevel, t);

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    manualSorting: false,
  });

  const totalCols = columns.length;

  return (
    <div className="space-y-3">
      {/* Pagination controls */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          Page {page}/{pages} &middot; {total.toLocaleString()} {total !== 1 ? t("eventTable.resultPlural") : t("eventTable.result")}
        </span>
        <div className="flex gap-1.5">
          <button
            disabled={page <= 1}
            onClick={() => onPageChange(1)}
            className="px-2 py-1 border border-border rounded-md text-xs hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            title={t("eventTable.firstPage")}
          >
            «
          </button>
          <button
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
            className="px-2.5 py-1 border border-border rounded-md text-xs hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            ‹ {t("eventTable.prev")}
          </button>
          <button
            disabled={page >= pages}
            onClick={() => onPageChange(page + 1)}
            className="px-2.5 py-1 border border-border rounded-md text-xs hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            {t("eventTable.next")} ›
          </button>
          <button
            disabled={page >= pages}
            onClick={() => onPageChange(pages)}
            className="px-2 py-1 border border-border rounded-md text-xs hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            title={t("eventTable.lastPage")}
          >
            »
          </button>
        </div>
      </div>

      <div className="overflow-x-auto border border-border rounded-xl shadow-sm">
        <table className="min-w-full text-sm">
          <thead className="bg-muted/50 border-b border-border">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((header) => (
                  <th
                    key={header.id}
                    className="px-3 py-2.5 text-left text-xs font-semibold text-muted-foreground whitespace-nowrap select-none cursor-pointer hover:bg-muted/80 hover:text-foreground transition-colors"
                    onClick={header.column.getToggleSortingHandler()}
                  >
                    {flexRender(
                      header.column.columnDef.header,
                      header.getContext()
                    )}
                    <span className="ml-1 text-muted-foreground/50">
                      {
                        { asc: "↑", desc: "↓" }[
                          header.column.getIsSorted() as string
                        ] ?? ""
                      }
                    </span>
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={totalCols} className="text-center py-10 text-muted-foreground">
                  <div className="flex items-center justify-center gap-2">
                    <div className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                    {t("eventTable.loading")}
                  </div>
                </td>
              </tr>
            ) : table.getRowModel().rows.length === 0 ? (
              <tr>
                <td colSpan={totalCols} className="text-center py-10 text-muted-foreground text-sm">
                  {t("eventTable.noResults")}
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  className="border-b border-border transition-colors hover:bg-muted/40"
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-3 py-2 whitespace-nowrap text-sm">
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext()
                      )}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
