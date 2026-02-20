"use client";
import { useState } from "react";
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  SortingState,
  getSortedRowModel,
  ColumnDef,
} from "@tanstack/react-table";
import type { SplicingEvent } from "@/types/event";
import { makeEventsColumns } from "./EventsTableColumns";

interface EventsTableProps {
  data: SplicingEvent[];
  total: number;
  page: number;
  pages: number;
  onPageChange: (p: number) => void;
  loading?: boolean;
  selectedIds: Set<string>;
  onToggleSelect: (id: string) => void;
  onSelectPage: (ids: string[]) => void;
  group1Label: string;
  group2Label: string;
  basketIds?: Set<string>;
  highlightTop10?: boolean;
  showIncLevel?: boolean;
}

export function EventsTable({
  data,
  total,
  page,
  pages,
  onPageChange,
  loading,
  selectedIds,
  onToggleSelect,
  onSelectPage,
  group1Label,
  group2Label,
  basketIds,
  highlightTop10 = true,
  showIncLevel = false,
}: EventsTableProps) {
  const [sorting, setSorting] = useState<SortingState>([]);

  const pageIds = data.map((e) => e.id);
  const allPageSelected =
    pageIds.length > 0 && pageIds.every((id) => selectedIds.has(id));
  const somePageSelected =
    !allPageSelected && pageIds.some((id) => selectedIds.has(id));

  const checkboxCol: ColumnDef<SplicingEvent, unknown> = {
    id: "select",
    header: () => (
      <input
        type="checkbox"
        checked={allPageSelected}
        ref={(el) => {
          if (el) el.indeterminate = somePageSelected;
        }}
        onChange={() => onSelectPage(pageIds)}
        onClick={(e) => e.stopPropagation()}
        className="rounded border-gray-300 cursor-pointer accent-blue-600"
        title="Sélectionner / désélectionner la page"
      />
    ),
    cell: ({ row }) => (
      <input
        type="checkbox"
        checked={selectedIds.has((row.original as SplicingEvent).id)}
        onChange={() => onToggleSelect((row.original as SplicingEvent).id)}
        onClick={(e) => e.stopPropagation()}
        className="rounded border-gray-300 cursor-pointer accent-blue-600"
      />
    ),
    size: 40,
  };

  const columns = [checkboxCol, ...makeEventsColumns(group1Label, group2Label, showIncLevel)];

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    manualSorting: false,
  });

  const totalCols = columns.length + 1;

  return (
    <div className="space-y-3">
      {/* Pagination controls */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          Page {page}/{pages} &middot; {total.toLocaleString("fr-FR")} résultat{total !== 1 ? "s" : ""}
        </span>
        <div className="flex gap-1.5">
          <button
            disabled={page <= 1}
            onClick={() => onPageChange(1)}
            className="px-2 py-1 border border-border rounded-md text-xs hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            title="Première page"
          >
            «
          </button>
          <button
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
            className="px-2.5 py-1 border border-border rounded-md text-xs hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            ‹ Préc.
          </button>
          <button
            disabled={page >= pages}
            onClick={() => onPageChange(page + 1)}
            className="px-2.5 py-1 border border-border rounded-md text-xs hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            Suiv. ›
          </button>
          <button
            disabled={page >= pages}
            onClick={() => onPageChange(pages)}
            className="px-2 py-1 border border-border rounded-md text-xs hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            title="Dernière page"
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
                  const isSelect = header.id === "select";
                  return (
                    <th
                      key={header.id}
                      className={`px-3 py-2.5 text-left text-xs font-semibold text-muted-foreground whitespace-nowrap select-none ${
                        isSelect ? "" : "cursor-pointer hover:bg-muted/80 hover:text-foreground transition-colors"
                      }`}
                      onClick={
                        isSelect
                          ? undefined
                          : header.column.getToggleSortingHandler()
                      }
                    >
                      {flexRender(
                        header.column.columnDef.header,
                        header.getContext()
                      )}
                      {!isSelect && (
                        <span className="ml-1 text-muted-foreground/50">
                          {
                            { asc: "↑", desc: "↓" }[
                              header.column.getIsSorted() as string
                            ] ?? ""
                          }
                        </span>
                      )}
                    </th>
                  );
                })}
                <th className="px-1 py-2.5 w-6" />
              </tr>
            ))}
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={totalCols} className="text-center py-10 text-muted-foreground">
                  <div className="flex items-center justify-center gap-2">
                    <div className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                    Chargement…
                  </div>
                </td>
              </tr>
            ) : table.getRowModel().rows.length === 0 ? (
              <tr>
                <td colSpan={totalCols} className="text-center py-10 text-muted-foreground text-sm">
                  Aucun résultat
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => {
                const event = row.original as SplicingEvent;
                const isTop10 = event.top_rank != null;
                const isSelected = selectedIds.has(event.id);
                const isInBasket = basketIds?.has(event.id) ?? false;

                const rowBg = isSelected
                  ? "bg-blue-50 dark:bg-blue-950/30 hover:bg-blue-100 dark:hover:bg-blue-950/50"
                  : isInBasket
                  ? "bg-green-50 dark:bg-green-950/20 hover:bg-green-100 dark:hover:bg-green-950/40"
                  : "hover:bg-muted/40";

                const top10Border =
                  isTop10 && highlightTop10 ? "border-l-[3px] border-l-blue-500" : "";

                return (
                  <tr
                    key={row.id}
                    className={`border-b border-border transition-colors cursor-pointer ${rowBg} ${top10Border}`}
                    onClick={() => onToggleSelect(event.id)}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="px-3 py-2 whitespace-nowrap text-sm">
                        {flexRender(
                          cell.column.columnDef.cell,
                          cell.getContext()
                        )}
                      </td>
                    ))}
                    <td className="px-1.5 py-2 w-6 text-center">
                      {isInBasket && (
                        <span title="Dans le panier" className="text-green-500">
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            className="w-3.5 h-3.5 inline"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                            strokeWidth={2}
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13l-1.4 7h12.8M9 21a1 1 0 100-2 1 1 0 000 2zm10 0a1 1 0 100-2 1 1 0 000 2z"
                            />
                          </svg>
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
