"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getAnalysis, listEvents } from "@/lib/api";
import { EventsTable } from "@/components/events/EventsTable";
import type { EventsQuery } from "@/lib/api";

export default function AnalysisDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [page, setPage] = useState(1);
  const [eventType, setEventType] = useState("");
  const [geneFilter, setGeneFilter] = useState("");
  const [fdrMax, setFdrMax] = useState("");
  const [sortBy, setSortBy] = useState<EventsQuery["sort_by"]>("fdr");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  const { data: analysis } = useQuery({
    queryKey: ["analysis", id],
    queryFn: () => getAnalysis(id),
  });

  const query: EventsQuery = {
    event_type: eventType || undefined,
    gene_symbol: geneFilter || undefined,
    fdr_max: fdrMax ? parseFloat(fdrMax) : undefined,
    sort_by: sortBy,
    sort_dir: sortDir,
    page,
    page_size: 50,
  };

  const { data: eventsPage, isLoading } = useQuery({
    queryKey: ["events", id, query],
    queryFn: () => listEvents(id, query),
    enabled: !!id,
  });

  const group1 = analysis?.sample_groups.find((g) => g.group_index === 1);
  const group2 = analysis?.sample_groups.find((g) => g.group_index === 2);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2 text-sm text-gray-400 mb-1">
            <Link href="/analyses" className="hover:text-gray-600">Analyses</Link>
            <span>/</span>
            <span>{analysis?.name ?? "..."}</span>
          </div>
          <h1 className="text-2xl font-bold">{analysis?.name}</h1>
          {group1 && group2 && (
            <p className="text-sm text-gray-500 mt-1">
              {group1.group_label} vs {group2.group_label}
            </p>
          )}
        </div>
        <Link
          href={`/analyses/${id}/top10`}
          className="bg-blue-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-blue-700"
        >
          Voir Top 10
        </Link>
      </div>

      {/* Filters */}
      <div className="bg-white border rounded-lg p-4 grid grid-cols-1 sm:grid-cols-4 gap-3">
        <select
          value={eventType}
          onChange={(e) => { setEventType(e.target.value); setPage(1); }}
          className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">Tous les types</option>
          {["SE", "RI", "A3SS", "A5SS", "MXE"].map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>

        <input
          type="text"
          placeholder="Gène (ex: PCBP1)"
          value={geneFilter}
          onChange={(e) => { setGeneFilter(e.target.value); setPage(1); }}
          className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />

        <input
          type="number"
          placeholder="FDR max (ex: 0.05)"
          value={fdrMax}
          onChange={(e) => { setFdrMax(e.target.value); setPage(1); }}
          min={0}
          max={1}
          step={0.01}
          className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />

        <select
          value={`${sortBy}_${sortDir}`}
          onChange={(e) => {
            const [col, dir] = e.target.value.split("_") as [EventsQuery["sort_by"], "asc" | "desc"];
            setSortBy(col); setSortDir(dir); setPage(1);
          }}
          className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="fdr_asc">FDR ↑</option>
          <option value="fdr_desc">FDR ↓</option>
          <option value="abs_inc_level_diff_desc">|ΔPSI| ↓</option>
          <option value="abs_inc_level_diff_asc">|ΔPSI| ↑</option>
          <option value="gene_symbol_asc">Gène A→Z</option>
        </select>
      </div>

      {/* Table */}
      {eventsPage && (
        <EventsTable
          data={eventsPage.items}
          total={eventsPage.total}
          page={eventsPage.page}
          pages={eventsPage.pages}
          onPageChange={setPage}
          loading={isLoading}
        />
      )}
      {!eventsPage && isLoading && (
        <p className="text-gray-400 text-sm">Chargement des événements...</p>
      )}
    </div>
  );
}
