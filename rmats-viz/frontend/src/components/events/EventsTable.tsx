"use client";
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  type SortingState,
} from "@tanstack/react-table";
import type { SplicingEvent } from "@/types/event";
import type { EventsQuery } from "@/lib/api/events";
import { makeEventsColumns } from "./EventsTableColumns";
import { useT } from "@/contexts/LanguageContext";

export type EventsSortBy = NonNullable<EventsQuery["sort_by"]>;
export type EventsSortDir = "asc" | "desc";

/** Column ids that the backend can sort on (see EventsQuery.sort_by). */
const SERVER_SORTABLE: ReadonlySet<string> = new Set<EventsSortBy>([
  "fdr",
  "gene_symbol",
  "abs_inc_level_diff",
]);

/** Default direction when a column is first clicked. */
const DEFAULT_DIR: Record<EventsSortBy, EventsSortDir> = {
  fdr: "asc",
  p_value: "asc",
  gene_symbol: "asc",
  abs_inc_level_diff: "desc",
};

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
  /** Current server-side sort (single source of truth lives in the page). */
  sortBy?: EventsSortBy;
  sortDir?: EventsSortDir;
  /** Called when a sortable header is clicked (E8). */
  onSortChange?: (sortBy: EventsSortBy, sortDir: EventsSortDir) => void;
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
  sortBy,
  sortDir = "asc",
  onSortChange,
}: EventsTableProps) {
  const t = useT();

  const columns = makeEventsColumns(group1Label, group2Label, showIncLevel, t);

  // Sorting is performed by the server; we only mirror the current sort so the
  // header indicator reflects it (manualSorting → no client-side re-ordering).
  const sorting: SortingState = sortBy ? [{ id: sortBy, desc: sortDir === "desc" }] : [];

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    enableSortingRemoval: false,
  });

  const totalCols = columns.length;

  const handleHeaderClick = (columnId: string) => {
    if (!onSortChange || !SERVER_SORTABLE.has(columnId)) return;
    const col = columnId as EventsSortBy;
    if (sortBy === col) {
      onSortChange(col, sortDir === "asc" ? "desc" : "asc");
    } else {
      onSortChange(col, DEFAULT_DIR[col]);
    }
  };

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
                {hg.headers.map((header) => {
                  const sortable = !!onSortChange && SERVER_SORTABLE.has(header.column.id);
                  const sorted = header.column.getIsSorted();
                  return (
                    <th
                      key={header.id}
                      className={`px-3 py-2.5 text-left text-xs font-semibold text-muted-foreground whitespace-nowrap select-none transition-colors ${
                        sortable ? "cursor-pointer hover:bg-muted/80 hover:text-foreground" : ""
                      }`}
                      onClick={sortable ? () => handleHeaderClick(header.column.id) : undefined}
                      aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : undefined}
                    >
                      {flexRender(
                        header.column.columnDef.header,
                        header.getContext()
                      )}
                      {sortable && (
                        <span className="ml-1 text-muted-foreground/50">
                          {sorted === "asc" ? "↑" : sorted === "desc" ? "↓" : ""}
                        </span>
                      )}
                    </th>
                  );
                })}
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
