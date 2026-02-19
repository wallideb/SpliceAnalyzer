"use client";
import { useState, useCallback } from "react";
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
  const [sortKey, setSortKey] = useState("fdr|asc");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const sortBy = sortKey.slice(0, sortKey.lastIndexOf("|")) as EventsQuery["sort_by"];
  const sortDir = sortKey.slice(sortKey.lastIndexOf("|") + 1) as "asc" | "desc";

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
  const group1Label = group1?.group_label ?? "Groupe 1";
  const group2Label = group2?.group_label ?? "Groupe 2";

  const handleToggleSelect = useCallback((eventId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(eventId)) next.delete(eventId);
      else next.add(eventId);
      return next;
    });
  }, []);

  const handleSelectPage = useCallback((ids: string[]) => {
    setSelectedIds((prev) => {
      const allSelected = ids.every((id) => prev.has(id));
      const next = new Set(prev);
      if (allSelected) ids.forEach((id) => next.delete(id));
      else ids.forEach((id) => next.add(id));
      return next;
    });
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2 text-sm text-gray-400 mb-1">
            <Link href="/analyses" className="hover:text-gray-600">
              Analyses
            </Link>
            <span>/</span>
            <span>{analysis?.name ?? "..."}</span>
          </div>
          <h1 className="text-2xl font-bold">{analysis?.name}</h1>
          {group1 && group2 && (
            <p className="text-sm text-gray-500 mt-1">
              <span className="text-red-600 font-medium">{group1Label}</span>
              {" vs "}
              <span className="text-blue-600 font-medium">{group2Label}</span>
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

      {/* Légende couleurs */}
      <div className="flex items-center gap-4 text-xs text-gray-500">
        <span className="font-medium text-gray-600">ΔPSI :</span>
        <span className="inline-flex items-center gap-1">
          <span className="w-3 h-3 rounded-sm bg-red-100 border border-red-300 inline-block" />
          <span className="text-red-700">positif → ↑ {group1Label}</span>
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="w-3 h-3 rounded-sm bg-blue-100 border border-blue-300 inline-block" />
          <span className="text-blue-700">négatif → ↑ {group2Label}</span>
        </span>
      </div>

      {/* Filters */}
      <div className="bg-white border rounded-lg p-4 grid grid-cols-1 sm:grid-cols-4 gap-3">
        <select
          value={eventType}
          onChange={(e) => {
            setEventType(e.target.value);
            setPage(1);
          }}
          className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">Tous les types</option>
          {["SE", "RI", "A3SS", "A5SS", "MXE"].map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>

        <input
          type="text"
          placeholder="Gène (ex: PCBP1)"
          value={geneFilter}
          onChange={(e) => {
            setGeneFilter(e.target.value);
            setPage(1);
          }}
          className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />

        <input
          type="number"
          placeholder="FDR max (ex: 0.05)"
          value={fdrMax}
          onChange={(e) => {
            setFdrMax(e.target.value);
            setPage(1);
          }}
          min={0}
          max={1}
          step={0.01}
          className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />

        <select
          value={sortKey}
          onChange={(e) => {
            setSortKey(e.target.value);
            setPage(1);
          }}
          className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="fdr|asc">FDR ↑</option>
          <option value="fdr|desc">FDR ↓</option>
          <option value="p_value|asc">p-value ↑</option>
          <option value="p_value|desc">p-value ↓</option>
          <option value="abs_inc_level_diff|desc">|ΔPSI| ↓</option>
          <option value="abs_inc_level_diff|asc">|ΔPSI| ↑</option>
          <option value="gene_symbol|asc">Gène A→Z</option>
        </select>
      </div>

      {/* Selection bar */}
      {selectedIds.size > 0 && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 flex items-center justify-between flex-wrap gap-2">
          <span className="text-sm text-blue-700 font-medium">
            {selectedIds.size} événement{selectedIds.size > 1 ? "s" : ""}{" "}
            sélectionné{selectedIds.size > 1 ? "s" : ""}
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setSelectedIds(new Set())}
              className="text-sm text-blue-600 hover:text-blue-800 underline"
            >
              Tout désélectionner
            </button>
            <button
              disabled
              title="Fonctionnalité à venir"
              className="bg-blue-600 text-white text-sm px-3 py-1 rounded opacity-50 cursor-not-allowed"
            >
              Poursuivre l&apos;analyse →
            </button>
          </div>
        </div>
      )}

      {/* Table */}
      {eventsPage && (
        <EventsTable
          data={eventsPage.items}
          total={eventsPage.total}
          page={eventsPage.page}
          pages={eventsPage.pages}
          onPageChange={setPage}
          loading={isLoading}
          selectedIds={selectedIds}
          onToggleSelect={handleToggleSelect}
          onSelectPage={handleSelectPage}
          group1Label={group1Label}
          group2Label={group2Label}
        />
      )}
      {!eventsPage && isLoading && (
        <p className="text-gray-400 text-sm">Chargement des événements...</p>
      )}
    </div>
  );
}
