"use client";
import { useState, useCallback, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getAnalysis, listEvents } from "@/lib/api";
import { EventsTable } from "@/components/events/EventsTable";
import { useBasket } from "@/contexts/BasketContext";
import type { EventsQuery } from "@/lib/api";

// ── Stat slider helpers ────────────────────────────────────────────────────────
// FDR / p-value: logarithmic scale 10^(-pos/10)
function logSliderToValue(pos: number): number {
  return Math.pow(10, -pos / 10);
}

function formatStatValue(val: number): string {
  if (val >= 1) return "1";
  if (val < 0.0001) return val.toExponential(1);
  return val.toPrecision(2);
}

// |ΔPSI|: linear 0–100 → 0.00–1.00
function dpsiSliderToValue(pos: number): number {
  return pos / 100;
}

export default function AnalysisDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { addItems, hasItem } = useBasket();

  const [page, setPage] = useState(1);
  const [eventType, setEventType] = useState("");
  const [geneFilter, setGeneFilter] = useState("");
  const [sortKey, setSortKey] = useState("fdr|asc");

  const [fdrSlider, setFdrSlider] = useState(0);
  const [pvalSlider, setPvalSlider] = useState(0);
  const [dpsiSlider, setDpsiSlider] = useState(0);

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [highlightTop10, setHighlightTop10] = useState(true);
  const [showIncLevel, setShowIncLevel] = useState(false);

  const sortBy = sortKey.slice(0, sortKey.lastIndexOf("|")) as EventsQuery["sort_by"];
  const sortDir = sortKey.slice(sortKey.lastIndexOf("|") + 1) as "asc" | "desc";

  const { data: analysis } = useQuery({
    queryKey: ["analysis", id],
    queryFn: () => getAnalysis(id),
  });

  const fdrMax = fdrSlider > 0 ? logSliderToValue(fdrSlider) : undefined;
  const pvalMax = pvalSlider > 0 ? logSliderToValue(pvalSlider) : undefined;
  const dpsiMin = dpsiSlider > 0 ? dpsiSliderToValue(dpsiSlider) : undefined;

  const query: EventsQuery = {
    event_type: eventType || undefined,
    gene_symbol: geneFilter || undefined,
    fdr_max: fdrMax,
    p_value_max: pvalMax,
    delta_psi_min: dpsiMin,
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

  const newCount = useMemo(() => {
    let n = 0;
    selectedIds.forEach((eid) => { if (!hasItem(eid)) n++; });
    return n;
  }, [selectedIds, hasItem]);

  const hasStatFilters = fdrSlider > 0 || pvalSlider > 0 || dpsiSlider > 0;

  return (
    <div className="space-y-5">
      {/* ── Header ── */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div className="min-w-0 flex-1">
          {/* Breadcrumb */}
          <nav className="flex items-center gap-1 text-sm text-muted-foreground mb-2">
            <Link href="/analyses" className="hover:text-foreground transition-colors inline-flex items-center gap-1">
              <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 22V12h6v10" />
              </svg>
              Analyses
            </Link>
            <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3 text-muted-foreground/50" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
            </svg>
            <span className="font-medium text-foreground truncate max-w-[300px]">{analysis?.name ?? "…"}</span>
          </nav>

          <h1 className="text-2xl font-extrabold tracking-tight text-foreground truncate">
            {analysis?.name ?? "…"}
          </h1>

          <div className="flex flex-wrap items-center gap-3 mt-2">
            {group1 && group2 && (
              <span className="text-sm">
                <span className="text-red-500 dark:text-red-400 font-semibold">{group1Label}</span>
                <span className="mx-1.5 text-muted-foreground">vs</span>
                <span className="text-blue-500 dark:text-blue-400 font-semibold">{group2Label}</span>
              </span>
            )}
            {analysis?.mutated_genes && analysis.mutated_genes.length > 0 && (
              <span className="flex items-center gap-1.5 flex-wrap">
                <span className="text-xs text-muted-foreground">Gène(s) muté(s) :</span>
                {analysis.mutated_genes.map((gene) => (
                  <span
                    key={typeof gene === "string" ? gene : gene.ensembl_id}
                    className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-bold bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300 border border-amber-200 dark:border-amber-700"
                  >
                    {typeof gene === "string" ? gene : gene.display}
                  </span>
                ))}
              </span>
            )}
          </div>
        </div>

        {/* Top10 actions */}
        <div className="flex items-center gap-2 shrink-0">
          <label className="flex items-center gap-1.5 cursor-pointer text-xs text-muted-foreground select-none hover:text-foreground transition-colors">
            <input
              type="checkbox"
              checked={highlightTop10}
              onChange={(e) => setHighlightTop10(e.target.checked)}
              className="rounded border-border accent-blue-600 cursor-pointer w-3.5 h-3.5"
            />
            Surligner Top 10
          </label>
          <Link
            href={`/analyses/${id}/top10`}
            className="inline-flex items-center gap-1.5 bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded-lg text-sm font-semibold transition-colors shadow-sm"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
            </svg>
            Top 10
          </Link>
        </div>
      </div>

      {/* ── Legend + event count ── */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span className="font-semibold text-foreground">ΔPSI :</span>
          <span className="inline-flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm bg-red-100 border border-red-300 dark:bg-red-950/40 dark:border-red-800" />
            <span className="text-red-600 dark:text-red-400">positif → ↑ {group1Label}</span>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm bg-blue-100 border border-blue-300 dark:bg-blue-950/40 dark:border-blue-800" />
            <span className="text-blue-600 dark:text-blue-400">négatif → ↑ {group2Label}</span>
          </span>
        </div>

        {/* Dynamic event count */}
        <div className={`inline-flex items-center gap-2 rounded-lg px-3 py-1.5 border transition-all ${
          isLoading
            ? "bg-muted border-border opacity-60"
            : "bg-blue-50 dark:bg-blue-950/30 border-blue-200 dark:border-blue-800"
        }`}>
          {isLoading ? (
            <div className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
          ) : (
            <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          )}
          <span className="text-sm font-bold text-blue-700 dark:text-blue-300 tabular-nums">
            {eventsPage?.total.toLocaleString("fr-FR") ?? "…"}
          </span>
          <span className="text-xs text-blue-500 dark:text-blue-400">
            événement{(eventsPage?.total ?? 0) !== 1 ? "s" : ""}
          </span>
        </div>
      </div>

      {/* ── Filters panel ── */}
      <div className="bg-card border border-border rounded-xl p-4 space-y-4 shadow-sm">
        {/* Row 1: type / gene / sort / incLevel toggle */}
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
          <select
            value={eventType}
            onChange={(e) => { setEventType(e.target.value); setPage(1); }}
            className="border border-border rounded-lg px-3 py-2 text-sm bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500 transition-shadow"
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
            className="border border-border rounded-lg px-3 py-2 text-sm bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-blue-500 transition-shadow"
          />

          <select
            value={sortKey}
            onChange={(e) => { setSortKey(e.target.value); setPage(1); }}
            className="border border-border rounded-lg px-3 py-2 text-sm bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500 transition-shadow"
          >
            <option value="fdr|asc">FDR ↑ croissant</option>
            <option value="fdr|desc">FDR ↓ décroissant</option>
            <option value="p_value|asc">p-value ↑</option>
            <option value="p_value|desc">p-value ↓</option>
            <option value="abs_inc_level_diff|desc">|ΔPSI| ↓ plus grand</option>
            <option value="abs_inc_level_diff|asc">|ΔPSI| ↑ plus petit</option>
            <option value="gene_symbol|asc">Gène A→Z</option>
          </select>

          <button
            onClick={() => setShowIncLevel((v) => !v)}
            title={showIncLevel ? "Masquer les niveaux d'inclusion" : "Afficher les niveaux d'inclusion"}
            className={`inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
              showIncLevel
                ? "bg-blue-600 text-white border-blue-600 shadow-sm"
                : "border-border text-muted-foreground hover:text-foreground hover:bg-muted"
            }`}
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              {showIncLevel ? (
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
              )}
            </svg>
            {showIncLevel ? "IncLevel visible" : "IncLevel masqué"}
          </button>
        </div>

        {/* Stat sliders — compact 3-column grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          <StatSlider
            label="FDR max"
            value={fdrSlider}
            onChange={(v) => { setFdrSlider(v); setPage(1); }}
            displayValue={fdrSlider > 0 ? `≤ ${formatStatValue(logSliderToValue(fdrSlider))}` : undefined}
            noFilterLabel="aucun filtre"
            max={100}
            ticks={["1", "0.1", "0.01", "1e-5", "1e-10"]}
          />
          <StatSlider
            label="p-value max"
            value={pvalSlider}
            onChange={(v) => { setPvalSlider(v); setPage(1); }}
            displayValue={pvalSlider > 0 ? `≤ ${formatStatValue(logSliderToValue(pvalSlider))}` : undefined}
            noFilterLabel="aucun filtre"
            max={100}
            ticks={["1", "0.1", "0.01", "1e-5", "1e-10"]}
          />
          <StatSlider
            label="|ΔPSI| min"
            value={dpsiSlider}
            onChange={(v) => { setDpsiSlider(v); setPage(1); }}
            displayValue={dpsiSlider > 0 ? `≥ ${dpsiSliderToValue(dpsiSlider).toFixed(2)}` : undefined}
            noFilterLabel="aucun filtre"
            max={100}
            ticks={["0", "0.1", "0.25", "0.5", "1"]}
            accentClass="accent-violet-600"
          />
        </div>

        {hasStatFilters && (
          <div className="flex items-start gap-2 text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-lg px-3 py-2 leading-relaxed">
            <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>
              Les <strong>Top 10 événements ◈</strong> sont sélectionnés selon les seuils rMATS par défaut
              (FDR &lt; 0.05, |ΔPSI| ≥ 0.1), classés par FDR puis |ΔPSI|. Ils restent toujours affichés
              indépendamment des filtres statistiques actifs.
            </span>
          </div>
        )}
      </div>

      {/* ── Selection / basket bar ── */}
      {selectedIds.size > 0 && (
        <div className="bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 rounded-xl px-4 py-3 flex items-center justify-between flex-wrap gap-2">
          <span className="text-sm text-blue-700 dark:text-blue-300 font-medium">
            {selectedIds.size} événement{selectedIds.size > 1 ? "s" : ""} sélectionné{selectedIds.size > 1 ? "s" : ""}
          </span>
          <div className="flex gap-2 items-center">
            <button
              onClick={() => setSelectedIds(new Set())}
              className="text-sm text-blue-600 dark:text-blue-400 hover:text-blue-800 underline"
            >
              Tout désélectionner
            </button>
            <button
              onClick={handleAddToBasket}
              disabled={newCount === 0}
              className="inline-flex items-center gap-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm px-3 py-1.5 rounded-lg disabled:opacity-40 disabled:cursor-not-allowed transition-colors font-medium"
              title={newCount === 0 ? "Tous ces événements sont déjà dans le panier" : undefined}
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13l-1.4 7h12.8M9 21a1 1 0 100-2 1 1 0 000 2zm10 0a1 1 0 100-2 1 1 0 000 2z" />
              </svg>
              {newCount > 0 ? `Ajouter au panier (${newCount})` : "Déjà dans le panier"}
            </button>
          </div>
        </div>
      )}

      {/* ── Events table ── */}
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
          highlightTop10={highlightTop10}
          showIncLevel={showIncLevel}
        />
      )}
      {!eventsPage && isLoading && (
        <div className="flex items-center gap-3 py-10 text-muted-foreground text-sm">
          <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          Chargement des événements…
        </div>
      )}
    </div>
  );
}

// ── StatSlider component ───────────────────────────────────────────────────────
function StatSlider({
  label,
  value,
  onChange,
  displayValue,
  noFilterLabel,
  max,
  ticks,
  accentClass = "accent-blue-600",
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  displayValue?: string;
  noFilterLabel: string;
  max: number;
  ticks: string[];
  accentClass?: string;
}) {
  const pct = (value / max) * 100;
  const isViolet = accentClass.includes("violet");

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-foreground">{label}</span>
        <div className="flex items-center gap-1">
          {displayValue ? (
            <span className={`text-xs font-bold px-2 py-0.5 rounded-md ${
              isViolet
                ? "text-violet-700 dark:text-violet-300 bg-violet-50 dark:bg-violet-950/40 border border-violet-200 dark:border-violet-800"
                : "text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800"
            }`}>
              {displayValue}
            </span>
          ) : (
            <span className="text-xs text-muted-foreground italic">{noFilterLabel}</span>
          )}
          <button
            onClick={() => onChange(0)}
            disabled={value === 0}
            className="w-5 h-5 flex items-center justify-center text-muted-foreground hover:text-destructive disabled:opacity-20 disabled:cursor-not-allowed transition-colors rounded"
            title="Réinitialiser"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      <input
        type="range"
        min={0}
        max={max}
        step={1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className={`stat-slider w-full ${accentClass}`}
        style={{ "--val": `${pct}%` } as React.CSSProperties}
      />

      <div className="flex justify-between text-[10px] text-muted-foreground/60 select-none">
        {ticks.map((t, i) => (
          <span key={i} className="text-center">{t}</span>
        ))}
      </div>
    </div>
  );
}
