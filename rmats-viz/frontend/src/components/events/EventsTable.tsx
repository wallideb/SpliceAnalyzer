"use client";
import { useState } from "react";
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  SortingState,
  getSortedRowModel,
  createColumnHelper,
  ColumnDef,
} from "@tanstack/react-table";
import type { SplicingEvent } from "@/types/event";
import { makeEventsColumns } from "./EventsTableColumns";

const colHelper = createColumnHelper<SplicingEvent>();

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
        className="rounded border-gray-300 cursor-pointer"
        title="Sélectionner / désélectionner la page"
      />
    ),
    cell: ({ row }) => (
      <input
        type="checkbox"
        checked={selectedIds.has((row.original as SplicingEvent).id)}
        onChange={() => onToggleSelect((row.original as SplicingEvent).id)}
        onClick={(e) => e.stopPropagation()}
        className="rounded border-gray-300 cursor-pointer"
      />
    ),
    size: 40,
  };

  const columns = [checkboxCol, ...makeEventsColumns(group1Label, group2Label)];

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
      <div className="text-sm text-gray-500">{total} événements</div>

      <div className="overflow-x-auto border rounded-lg">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50 border-b">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((header) => {
                  const isSelect = header.id === "select";
                  return (
                    <th
                      key={header.id}
                      className={`px-3 py-2 text-left text-xs font-semibold text-gray-600 whitespace-nowrap select-none ${
                        isSelect ? "" : "cursor-pointer hover:bg-gray-100"
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
                        <span className="ml-1 text-gray-400">
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
              </tr>
            ))}
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td
                  colSpan={totalCols}
                  className="text-center py-8 text-gray-400"
                >
                  Chargement...
                </td>
              </tr>
            ) : table.getRowModel().rows.length === 0 ? (
              <tr>
                <td
                  colSpan={totalCols}
                  className="text-center py-8 text-gray-400"
                >
                  Aucun résultat
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => {
                const event = row.original as SplicingEvent;
                const isTop10 = event.top_rank != null;
                const isSelected = selectedIds.has(event.id);
                return (
                  <tr
                    key={row.id}
                    className={`border-b transition-colors cursor-pointer ${
                      isSelected
                        ? "bg-blue-50 hover:bg-blue-100"
                        : "hover:bg-gray-50"
                    } ${isTop10 ? "border-l-4 border-l-blue-500" : ""}`}
                    onClick={() => onToggleSelect(event.id)}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="px-3 py-2 whitespace-nowrap">
                        {flexRender(
                          cell.column.columnDef.cell,
                          cell.getContext()
                        )}
                      </td>
                    ))}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between text-sm text-gray-500">
        <span>
          Page {page} / {pages}
        </span>
        <div className="flex gap-2">
          <button
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
            className="px-3 py-1 border rounded hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            ←
          </button>
          <button
            disabled={page >= pages}
            onClick={() => onPageChange(page + 1)}
            className="px-3 py-1 border rounded hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            →
          </button>
        </div>
      </div>
    </div>
  );
}
