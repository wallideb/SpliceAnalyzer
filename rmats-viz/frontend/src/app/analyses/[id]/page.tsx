"use client";
import { useState, useCallback, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getAnalysis, listEvents } from "@/lib/api";
import { EventsTable } from "@/components/events/EventsTable";
import { useBasket } from "@/contexts/BasketContext";
import type { EventsQuery } from "@/lib/api";

// ── Log-scale helpers ─────────────────────────────────────────────────────────
// Slider position 0–100 maps to: 10^(-pos / 10)
// pos=0  → 1.0   (no filter active)
// pos=10 → 0.1
// pos=20 → 0.01
// pos=50 → 1e-5
// pos=100→ 1e-10
function sliderToValue(pos: number): number {
  return Math.pow(10, -pos / 10);
}

function formatStatValue(val: number): string {
  if (val >= 1) return "1";
  if (val < 0.0001) return val.toExponential(1);
  return val.toPrecision(2);
}

export default function AnalysisDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { addItems, hasItem, count: basketCount } = useBasket();

  const [page, setPage] = useState(1);
  const [eventType, setEventType] = useState("");
  const [geneFilter, setGeneFilter] = useState("");
  const [sortKey, setSortKey] = useState("fdr|asc");

  // Slider positions (0 = no filter / value=1, 100 = most restrictive)
  const [fdrSlider, setFdrSlider] = useState(0);   // 0 means no FDR filter
  const [pvalSlider, setPvalSlider] = useState(0);  // 0 means no p-value filter

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const sortBy = sortKey.slice(0, sortKey.lastIndexOf("|")) as EventsQuery["sort_by"];
  const sortDir = sortKey.slice(sortKey.lastIndexOf("|") + 1) as "asc" | "desc";

  const { data: analysis } = useQuery({
    queryKey: ["analysis", id],
    queryFn: () => getAnalysis(id),
  });

  const fdrMax = fdrSlider > 0 ? sliderToValue(fdrSlider) : undefined;
  const pvalMax = pvalSlider > 0 ? sliderToValue(pvalSlider) : undefined;

  const query: EventsQuery = {
    event_type: eventType || undefined,
    gene_symbol: geneFilter || undefined,
    fdr_max: fdrMax,
    p_value_max: pvalMax,
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
  const analysisName = analysis?.name ?? "";

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

  const handleAddToBasket = useCallback(() => {
    if (!eventsPage || selectedIds.size === 0) return;
    const selectedEvents = eventsPage.items.filter((e) => selectedIds.has(e.id));
    addItems(
      selectedEvents.map((event) => ({
        event,
        analysisId: id,
        analysisName,
        addedAt: new Date().toISOString(),
      }))
    );
    setSelectedIds(new Set());
  }, [eventsPage, selectedIds, addItems, id, analysisName]);

  // Count how many selected events are already in the basket
  const newCount = useMemo(() => {
    let n = 0;
    selectedIds.forEach((eid) => { if (!hasItem(eid)) n++; });
    return n;
  }, [selectedIds, hasItem]);

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
      <div className="bg-white border rounded-lg p-4 space-y-4">
        {/* Row 1: type / gene / sort */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
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

          <select
            value={sortKey}
            onChange={(e) => { setSortKey(e.target.value); setPage(1); }}
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

        {/* Row 2: FDR slider */}
        <div className="space-y-1">
          <div className="flex items-center justify-between text-xs">
            <label className="font-medium text-gray-600">
              FDR max
              {fdrSlider > 0 && (
                <span className="ml-1 text-blue-600">≤ {formatStatValue(sliderToValue(fdrSlider))}</span>
              )}
              {fdrSlider === 0 && (
                <span className="ml-1 text-gray-400">(pas de filtre)</span>
              )}
            </label>
            <button
              onClick={() => { setFdrSlider(0); setPage(1); }}
              disabled={fdrSlider === 0}
              className="text-gray-400 hover:text-red-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              title="Réinitialiser FDR"
            >
              ✕
            </button>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-400 w-6">1</span>
            <input
              type="range"
              min={0}
              max={100}
              step={1}
              value={fdrSlider}
              onChange={(e) => { setFdrSlider(Number(e.target.value)); setPage(1); }}
              className="flex-1 accent-blue-600 cursor-pointer"
            />
            <span className="text-xs text-gray-400 w-14 text-right">10⁻¹⁰</span>
          </div>
          <div className="flex justify-between text-xs text-gray-300 px-9">
            <span>0.1</span>
            <span>0.01</span>
            <span>1e-5</span>
          </div>
        </div>

        {/* Row 3: p-value slider */}
        <div className="space-y-1">
          <div className="flex items-center justify-between text-xs">
            <label className="font-medium text-gray-600">
              p-value max
              {pvalSlider > 0 && (
                <span className="ml-1 text-blue-600">≤ {formatStatValue(sliderToValue(pvalSlider))}</span>
              )}
              {pvalSlider === 0 && (
                <span className="ml-1 text-gray-400">(pas de filtre)</span>
              )}
            </label>
            <button
              onClick={() => { setPvalSlider(0); setPage(1); }}
              disabled={pvalSlider === 0}
              className="text-gray-400 hover:text-red-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              title="Réinitialiser p-value"
            >
              ✕
            </button>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-400 w-6">1</span>
            <input
              type="range"
              min={0}
              max={100}
              step={1}
              value={pvalSlider}
              onChange={(e) => { setPvalSlider(Number(e.target.value)); setPage(1); }}
              className="flex-1 accent-blue-600 cursor-pointer"
            />
            <span className="text-xs text-gray-400 w-14 text-right">10⁻¹⁰</span>
          </div>
          <div className="flex justify-between text-xs text-gray-300 px-9">
            <span>0.1</span>
            <span>0.01</span>
            <span>1e-5</span>
          </div>
        </div>

        {(fdrSlider > 0 || pvalSlider > 0) && (
          <p className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded px-3 py-1.5">
            Les <strong>Top 10</strong> événements (marqués ◈) restent toujours affichés indépendamment des seuils statistiques.
          </p>
        )}
      </div>

      {/* Selection / basket bar */}
      {selectedIds.size > 0 && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 flex items-center justify-between flex-wrap gap-2">
          <span className="text-sm text-blue-700 font-medium">
            {selectedIds.size} événement{selectedIds.size > 1 ? "s" : ""}{" "}
            sélectionné{selectedIds.size > 1 ? "s" : ""}
          </span>
          <div className="flex gap-2 items-center">
            <button
              onClick={() => setSelectedIds(new Set())}
              className="text-sm text-blue-600 hover:text-blue-800 underline"
            >
              Tout désélectionner
            </button>
            <button
              onClick={handleAddToBasket}
              disabled={newCount === 0}
              className="bg-blue-600 text-white text-sm px-3 py-1.5 rounded-md hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              title={newCount === 0 ? "Tous ces événements sont déjà dans le panier" : undefined}
            >
              {newCount > 0
                ? `Ajouter au panier (${newCount})`
                : "Déjà dans le panier"}
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
          basketIds={new Set(
            eventsPage.items.filter((e) => hasItem(e.id)).map((e) => e.id)
          )}
        />
      )}
      {!eventsPage && isLoading && (
        <p className="text-gray-400 text-sm">Chargement des événements...</p>
      )}
    </div>
  );
}
