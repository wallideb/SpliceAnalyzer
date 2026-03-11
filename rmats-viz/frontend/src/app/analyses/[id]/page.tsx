"use client";
import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getAnalysis, listEvents, downloadAnalysisExcel, downloadAnalysisPDF, getManhattanData } from "@/lib/api";
import { EventsTable } from "@/components/events/EventsTable";
import { ManhattanPlot } from "@/components/events/ManhattanPlot";
import { MutatedGenePanel } from "@/components/top10/MutatedGenePanel";
import { ScienceNote } from "@/components/ScienceNote";
import { ExcelExportModal, type ExcelColumnGroup } from "@/components/ExcelExportModal";
import { useT, useLanguage } from "@/contexts/LanguageContext";
import type { EventsQuery } from "@/lib/api";
import type { GeneEntry } from "@/types/gene";

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
  const t = useT();
  const { lang } = useLanguage();

  const [page, setPage] = useState(1);
  const [eventType, setEventType] = useState("");
  const [geneFilter, setGeneFilter] = useState("");
  const [sortKey, setSortKey] = useState("fdr|asc");

  const [fdrSlider, setFdrSlider] = useState(0);
  const [pvalSlider, setPvalSlider] = useState(0);
  const [dpsiSlider, setDpsiSlider] = useState(0);

  const [isExporting, setIsExporting] = useState(false);
  const [isExportingPDF, setIsExportingPDF] = useState(false);
  const [showExcelModal, setShowExcelModal] = useState(false);
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

  // Manhattan plot data (all events, lightweight)
  const { data: manhattanData = [], isLoading: loadingManhattan } = useQuery({
    queryKey: ["manhattan", id],
    queryFn: () => getManhattanData(id),
    enabled: !!id,
    staleTime: 5 * 60 * 1000, // 5 min cache
  });

  const [showManhattan, setShowManhattan] = useState(false);

  const group1 = analysis?.sample_groups.find((g) => g.group_index === 1);
  const group2 = analysis?.sample_groups.find((g) => g.group_index === 2);
  const group1Label = group1?.group_label ?? "Group 1";
  const group2Label = group2?.group_label ?? "Group 2";
  const analysisName = analysis?.name ?? "";

  // Resolved mutated gene entries (guard against legacy string format)
  const mutatedGenes: GeneEntry[] = (analysis?.mutated_genes ?? []).filter(
    (g): g is GeneEntry => typeof g === "object" && "ensembl_id" in g,
  );

  const handleExport = useCallback(async (groups: ExcelColumnGroup[] = ["core"]) => {
    setIsExporting(true);
    setShowExcelModal(false);
    try {
      await downloadAnalysisExcel(id, groups);
    } catch {
      alert(t("analysisDetail.excelError"));
    } finally {
      setIsExporting(false);
    }
  }, [id, t]);

  const handleExportPDF = useCallback(async () => {
    setIsExportingPDF(true);
    try {
      await downloadAnalysisPDF(id);
    } catch {
      alert(t("analysisDetail.pdfError"));
    } finally {
      setIsExportingPDF(false);
    }
  }, [id]);

  return (
    <div className="flex gap-6 items-start">

      {/* ══ LEFT STICKY SIDEBAR – Gene cards ══════════════════════════════ */}
      {mutatedGenes.length > 0 && (
        <aside className="sticky top-20 self-start w-60 shrink-0 z-10">
          {/* Sidebar header */}
          <div className="flex items-center gap-1.5 mb-2 px-1">
            <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5 text-amber-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" />
            </svg>
            <span className="text-[10px] font-bold text-amber-700 dark:text-amber-400 uppercase tracking-wider">
              {t("analysisDetail.candidateGenes")}
            </span>
          </div>
          {/* Cards – scrollable if many genes */}
          <div className="max-h-[calc(100vh-6rem)] overflow-y-auto space-y-3 pr-1"
            style={{ scrollbarWidth: "thin", scrollbarColor: "rgb(251 191 36 / 0.3) transparent" }}
          >
            <MutatedGenePanel mutatedGenes={mutatedGenes} analysisId={id} layout="vertical" />
          </div>
        </aside>
      )}

      {/* ══ MAIN CONTENT ══════════════════════════════════════════════════ */}
      <div className="flex-1 min-w-0 space-y-5">

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
              {t("analysisDetail.breadcrumb")}
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
                <span className="text-xs text-muted-foreground">{t("analysisDetail.mutatedGenes")}</span>
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

        {/* Actions */}
        <div className="flex items-center gap-2 shrink-0 flex-wrap">
          <button
            onClick={() => setShowExcelModal(true)}
            disabled={isExporting}
            className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg disabled:opacity-50 transition-colors"
          >
            {isExporting ? <SpinnerIcon /> : <DownloadIcon />}
            {isExporting ? "Export…" : t("analysisDetail.excel")}
          </button>
          <button
            onClick={handleExportPDF}
            disabled={isExportingPDF}
            className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-semibold bg-rose-600 hover:bg-rose-700 text-white rounded-lg disabled:opacity-50 transition-colors"
          >
            {isExportingPDF ? <SpinnerIcon /> : <DownloadIcon />}
            {isExportingPDF ? "PDF…" : t("analysisDetail.pdf")}
          </button>
          <Link
            href={`/analyses/${id}/deep-analysis`}
            className="inline-flex items-center gap-1.5 bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded-lg text-sm font-semibold transition-colors shadow-sm"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            {t("analysisDetail.deepAnalysis")}
          </Link>
        </div>
      </div>

      {/* ── Legend + event count ── */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span className="font-semibold text-foreground">{t("analysisDetail.legend.deltaLabel")}</span>
          <span className="inline-flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm bg-red-100 border border-red-300 dark:bg-red-950/40 dark:border-red-800" />
            <span className="text-red-600 dark:text-red-400">{t("analysisDetail.legend.negative", { group: group1Label })}</span>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm bg-blue-100 border border-blue-300 dark:bg-blue-950/40 dark:border-blue-800" />
            <span className="text-blue-600 dark:text-blue-400">{t("analysisDetail.legend.positive", { group: group1Label })}</span>
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
            {eventsPage?.total.toLocaleString(lang === "fr" ? "fr-FR" : "en-GB") ?? "…"}
          </span>
          <span className="text-xs text-blue-500 dark:text-blue-400">
            {(eventsPage?.total ?? 0) !== 1 ? t("analysisDetail.eventsPlural") : t("analysisDetail.events")}
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
            <option value="">{t("analysisDetail.filters.allTypes")}</option>
            {["SE", "RI", "A3SS", "A5SS", "MXE"].map((et) => (
              <option key={et} value={et}>{et}</option>
            ))}
          </select>

          <input
            type="text"
            placeholder={t("analysisDetail.filters.genePlaceholder")}
            value={geneFilter}
            onChange={(e) => { setGeneFilter(e.target.value); setPage(1); }}
            className="border border-border rounded-lg px-3 py-2 text-sm bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-blue-500 transition-shadow"
          />

          <select
            value={sortKey}
            onChange={(e) => { setSortKey(e.target.value); setPage(1); }}
            className="border border-border rounded-lg px-3 py-2 text-sm bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500 transition-shadow"
          >
            <option value="fdr|asc">{t("analysisDetail.filters.sortFdrAsc")}</option>
            <option value="fdr|desc">{t("analysisDetail.filters.sortFdrDesc")}</option>
            <option value="p_value|asc">{t("analysisDetail.filters.sortPvalAsc")}</option>
            <option value="p_value|desc">{t("analysisDetail.filters.sortPvalDesc")}</option>
            <option value="abs_inc_level_diff|desc">{t("analysisDetail.filters.sortDpsiDesc")}</option>
            <option value="abs_inc_level_diff|asc">{t("analysisDetail.filters.sortDpsiAsc")}</option>
            <option value="gene_symbol|asc">{t("analysisDetail.filters.sortGeneAz")}</option>
          </select>

          <button
            onClick={() => setShowIncLevel((v) => !v)}
            title={showIncLevel ? t("analysisDetail.filters.hideIncLevel") : t("analysisDetail.filters.showIncLevel")}
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
            {showIncLevel ? t("analysisDetail.filters.incLevelVisible") : t("analysisDetail.filters.incLevelHidden")}
          </button>
        </div>

        {/* Stat sliders — compact 3-column grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          <StatSlider
            label="FDR max"
            value={fdrSlider}
            onChange={(v) => { setFdrSlider(v); setPage(1); }}
            displayValue={fdrSlider > 0 ? `≤ ${formatStatValue(logSliderToValue(fdrSlider))}` : undefined}
            noFilterLabel={t("analysisDetail.filters.noFilter")}
            max={100}
            ticks={["1", "0.1", "0.01", "1e-5", "1e-10"]}
          />
          <StatSlider
            label="p-value max"
            value={pvalSlider}
            onChange={(v) => { setPvalSlider(v); setPage(1); }}
            displayValue={pvalSlider > 0 ? `≤ ${formatStatValue(logSliderToValue(pvalSlider))}` : undefined}
            noFilterLabel={t("analysisDetail.filters.noFilter")}
            max={100}
            ticks={["1", "0.1", "0.01", "1e-5", "1e-10"]}
          />
          <StatSlider
            label="|ΔPSI| min"
            value={dpsiSlider}
            onChange={(v) => { setDpsiSlider(v); setPage(1); }}
            displayValue={dpsiSlider > 0 ? `≥ ${dpsiSliderToValue(dpsiSlider).toFixed(2)}` : undefined}
            noFilterLabel={t("analysisDetail.filters.noFilter")}
            max={100}
            ticks={["0", "0.1", "0.25", "0.5", "1"]}
            accentClass="accent-violet-600"
            logScale={false}
          />
        </div>

      </div>

      {/* ── Manhattan plot toggle + panel ── */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => setShowManhattan((v) => !v)}
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
            showManhattan
              ? "bg-emerald-600 text-white border-emerald-600 shadow-sm"
              : "border-border text-muted-foreground hover:text-foreground hover:bg-muted"
          }`}
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
          </svg>
          {t("manhattan.toggle")}
        </button>
      </div>

      {showManhattan && (
        <ManhattanPlot
          data={manhattanData}
          loading={loadingManhattan}
          mutatedGenes={mutatedGenes.map((g) => ({ symbol: g.symbol, ensembl_id: g.ensembl_id }))}
          onEventClick={(eventId) => {
            const evt = manhattanData.find((d) => d.id === eventId);
            if (evt?.gene_symbol) {
              setGeneFilter(evt.gene_symbol);
              setPage(1);
              // Scroll to table
              document.getElementById("events-table")?.scrollIntoView({ behavior: "smooth", block: "start" });
            }
          }}
        />
      )}

      {/* ── Events table ── */}
      <div id="events-table" />
      {eventsPage && (
        <EventsTable
          data={eventsPage.items}
          total={eventsPage.total}
          page={eventsPage.page}
          pages={eventsPage.pages}
          onPageChange={setPage}
          loading={isLoading}
          group1Label={group1Label}
          group2Label={group2Label}
          showIncLevel={showIncLevel}
        />
      )}
      {!eventsPage && isLoading && (
        <div className="flex items-center gap-3 py-10 text-muted-foreground text-sm">
          <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          {t("analysisDetail.loading")}
        </div>
      )}

      {/* ── Statistical methodology note ── */}
      <ScienceNote
        title={t("scienceNotes.exonDiagram.title")}
        body={t("scienceNotes.exonDiagram.body")}
        refs={["rmats", "benjamini_hochberg", "mane_select"]}
      />

      </div>{/* end main content */}

      {/* ══ EXCEL EXPORT MODAL ══════════════════════════════════════════════ */}
      <ExcelExportModal
        isOpen={showExcelModal}
        onClose={() => setShowExcelModal(false)}
        onDownload={handleExport}
        isDownloading={isExporting}
      />

    </div>
  );
}

// ── Export icon components ─────────────────────────────────────────────────────
function DownloadIcon() {
  return (
    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
    </svg>
  );
}

function SpinnerIcon() {
  return (
    <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth={4} />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  );
}

// ── StatSlider component ───────────────────────────────────────────────────────

/** Convert a real value back to slider position (inverse of logSliderToValue). */
function valueToLogSlider(val: number): number {
  if (val <= 0 || val >= 1) return 0;
  return Math.round(-Math.log10(val) * 10);
}

/** Convert a real ΔPSI value back to slider position (inverse of dpsiSliderToValue). */
function valueToDpsiSlider(val: number): number {
  return Math.round(val * 100);
}

function StatSlider({
  label,
  value,
  onChange,
  displayValue,
  noFilterLabel,
  max,
  ticks,
  accentClass = "accent-blue-600",
  /** If true, use log scale (FDR/p-value). If false, use linear (ΔPSI). */
  logScale = true,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  displayValue?: string;
  noFilterLabel: string;
  max: number;
  ticks: string[];
  accentClass?: string;
  logScale?: boolean;
}) {
  const t = useT();
  const [inputText, setInputText] = useState("");
  const [showInput, setShowInput] = useState(false);
  const pct = (value / max) * 100;
  const isViolet = accentClass.includes("violet");

  const handleDirectInput = () => {
    const num = parseFloat(inputText);
    if (isNaN(num) || num <= 0) {
      onChange(0);
    } else if (logScale) {
      // Clamp to valid range for log scale
      const clamped = Math.max(1e-10, Math.min(1, num));
      onChange(Math.min(max, valueToLogSlider(clamped)));
    } else {
      const clamped = Math.max(0, Math.min(1, num));
      onChange(Math.min(max, valueToDpsiSlider(clamped)));
    }
    setShowInput(false);
    setInputText("");
  };

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-foreground">{label}</span>
        <div className="flex items-center gap-1">
          {showInput ? (
            <input
              type="text"
              autoFocus
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onBlur={handleDirectInput}
              onKeyDown={(e) => { if (e.key === "Enter") handleDirectInput(); if (e.key === "Escape") { setShowInput(false); setInputText(""); } }}
              placeholder={logScale ? "e.g. 0.05" : "e.g. 0.1"}
              className={`w-20 text-xs font-mono px-1.5 py-0.5 rounded-md border bg-background text-foreground focus:outline-none focus:ring-1 ${
                isViolet ? "border-violet-300 focus:ring-violet-500" : "border-blue-300 focus:ring-blue-500"
              }`}
            />
          ) : displayValue ? (
            <button
              onClick={() => setShowInput(true)}
              title="Click to enter value"
              className={`text-xs font-bold px-2 py-0.5 rounded-md cursor-text hover:ring-1 transition-shadow ${
                isViolet
                  ? "text-violet-700 dark:text-violet-300 bg-violet-50 dark:bg-violet-950/40 border border-violet-200 dark:border-violet-800 hover:ring-violet-400"
                  : "text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800 hover:ring-blue-400"
              }`}
            >
              {displayValue}
            </button>
          ) : (
            <button
              onClick={() => setShowInput(true)}
              className="text-xs text-muted-foreground italic hover:text-foreground transition-colors cursor-text"
            >
              {noFilterLabel}
            </button>
          )}
          <button
            onClick={() => onChange(0)}
            disabled={value === 0}
            className="w-5 h-5 flex items-center justify-center text-muted-foreground hover:text-destructive disabled:opacity-20 disabled:cursor-not-allowed transition-colors rounded"
            title={t("analysisDetail.filters.reset")}
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
        {ticks.map((tk, i) => (
          <span key={i} className="text-center">{tk}</span>
        ))}
      </div>
    </div>
  );
}
