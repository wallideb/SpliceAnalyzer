"use client";

/**
 * HnRNPMotifPanel
 * ================
 * Displays hnRNP motif enrichment analysis results: proportion of known
 * RNA-binding protein motifs in significant vs background events, across
 * five genomic regions around skipped exons.
 *
 * Inspired by rMAPS2 (Hwang et al., NAR 2020).
 *
 * Data: GET /api/v1/deep-analyses/{id}/hnrnp-motifs
 */

import { useQuery } from "@tanstack/react-query";
import { useState, useMemo } from "react";
import { fetchJSON, BASE } from "@/lib/api/client";
import { ScienceNote } from "@/components/ScienceNote";
import { useT } from "@/contexts/LanguageContext";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface MotifEnrichmentItem {
  motif_name: string;
  protein: string;
  region: string;
  sig_hit_count: number;
  sig_total: number;
  bg_hit_count: number;
  bg_total: number;
  sig_density: number;
  bg_density: number;
  z_stat: number | null;
  p_value: number | null;
  p_adjusted: number | null;
  significant: boolean;
}

interface HnRNPMotifResponse {
  n_sig_events: number;
  n_bg_events: number;
  results: MotifEnrichmentItem[];
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

function getHnRNPMotifs(deepId: string): Promise<HnRNPMotifResponse> {
  return fetchJSON(`${BASE}/deep-analyses/${deepId}/hnrnp-motifs`);
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const REGION_LABELS: Record<string, string> = {
  upstream_exon: "Upstream exon",
  upstream_intron: "Upstream intron",
  skipped_exon: "Skipped exon",
  downstream_intron: "Downstream intron",
  downstream_exon: "Downstream exon",
};

const REGION_ORDER = [
  "upstream_exon",
  "upstream_intron",
  "skipped_exon",
  "downstream_intron",
  "downstream_exon",
];

const PROTEIN_COLORS: Record<string, string> = {
  "hnRNP A1/A2":      "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300 border-red-200 dark:border-red-800",
  "hnRNP E1 (PCBP1)": "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300 border-rose-200 dark:border-rose-800",
  "hnRNP E2 (PCBP2)": "bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-300 border-pink-200 dark:border-pink-800",
  "hnRNP F/H":        "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300 border-green-200 dark:border-green-800",
  "hnRNP K":          "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300 border-blue-200 dark:border-blue-800",
  "hnRNP C":          "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300 border-purple-200 dark:border-purple-800",
  "hnRNP L":          "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300 border-amber-200 dark:border-amber-800",
  "hnRNP M":          "bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-300 border-teal-200 dark:border-teal-800",
  "PTB (hnRNP I)":    "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300 border-orange-200 dark:border-orange-800",
};

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface HnRNPMotifPanelProps {
  deepAnalysisId: string;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function HnRNPMotifPanel({ deepAnalysisId }: HnRNPMotifPanelProps) {
  const t = useT();
  const [showAll, setShowAll] = useState(false);
  const [selectedProtein, setSelectedProtein] = useState<string | null>(null);
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["hnrnp-motifs", deepAnalysisId],
    queryFn: () => getHnRNPMotifs(deepAnalysisId),
    enabled: !!deepAnalysisId,
    staleTime: 10 * 60 * 1000,
  });

  // Unique protein families
  const proteins = useMemo(() => {
    if (!data) return [];
    return [...new Set(data.results.map((r) => r.protein))];
  }, [data]);

  // Filter & sort results
  const filteredResults = useMemo(() => {
    if (!data) return [];
    let results = data.results;
    if (!showAll) {
      results = results.filter((r) => r.significant);
    }
    if (selectedProtein) {
      results = results.filter((r) => r.protein === selectedProtein);
    }
    if (selectedRegion) {
      results = results.filter((r) => r.region === selectedRegion);
    }
    // Sort by p_adjusted ascending (most significant first)
    return [...results].sort((a, b) => {
      if (a.p_adjusted === null) return 1;
      if (b.p_adjusted === null) return -1;
      return a.p_adjusted - b.p_adjusted;
    });
  }, [data, showAll, selectedProtein, selectedRegion]);

  // Significant count
  const nSignificant = useMemo(
    () => data?.results.filter((r) => r.significant).length ?? 0,
    [data],
  );

  // ── Loading ────────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="space-y-3 p-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-6 rounded bg-muted animate-pulse" />
        ))}
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex flex-col items-center gap-3 py-8 text-center">
        <p className="text-sm text-muted-foreground">{t("hnrnpPanel.error")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-5 text-xs">
      {/* Summary */}
      <div className="flex flex-wrap gap-3">
        <SummaryChip label={t("hnrnpPanel.sigEvents")} value={data.n_sig_events} />
        <SummaryChip label={t("hnrnpPanel.bgEvents")} value={data.n_bg_events} />
        <SummaryChip label={t("hnrnpPanel.significantMotifs")} value={nSignificant} highlight />
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2 p-2 rounded-lg bg-muted/30 border border-border">
        <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mr-1">
          {t("hnrnpPanel.filters")}
        </span>

        {/* Show all / significant only toggle */}
        <button
          onClick={() => setShowAll((v) => !v)}
          className={`px-2 py-0.5 text-[10px] font-semibold rounded border transition-colors ${
            showAll
              ? "bg-card border-border text-muted-foreground"
              : "bg-green-600 border-green-600 text-white"
          }`}
        >
          {showAll ? t("hnrnpPanel.showAll") : t("hnrnpPanel.significantOnly")}
        </button>

        {/* Protein filter */}
        <select
          value={selectedProtein ?? ""}
          onChange={(e) => setSelectedProtein(e.target.value || null)}
          className="px-2 py-0.5 text-[10px] rounded border border-border bg-card text-foreground"
        >
          <option value="">{t("hnrnpPanel.allProteins")}</option>
          {proteins.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>

        {/* Region filter */}
        <select
          value={selectedRegion ?? ""}
          onChange={(e) => setSelectedRegion(e.target.value || null)}
          className="px-2 py-0.5 text-[10px] rounded border border-border bg-card text-foreground"
        >
          <option value="">{t("hnrnpPanel.allRegions")}</option>
          {REGION_ORDER.map((r) => (
            <option key={r} value={r}>{REGION_LABELS[r]}</option>
          ))}
        </select>
      </div>

      {/* Results table */}
      {filteredResults.length === 0 ? (
        <p className="text-sm text-muted-foreground text-center py-4">
          {showAll ? t("hnrnpPanel.noResults") : t("hnrnpPanel.noSignificant")}
        </p>
      ) : (
        <div className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-muted/50 border-b border-border">
                <tr>
                  <th className="px-3 py-2 text-left font-semibold text-muted-foreground">{t("hnrnpPanel.colProtein")}</th>
                  <th className="px-3 py-2 text-left font-semibold text-muted-foreground">{t("hnrnpPanel.colMotif")}</th>
                  <th className="px-3 py-2 text-left font-semibold text-muted-foreground">{t("hnrnpPanel.colRegion")}</th>
                  <th className="px-3 py-2 text-center font-semibold text-green-700 dark:text-green-400">{t("hnrnpPanel.colSig")}</th>
                  <th className="px-3 py-2 text-center font-semibold text-slate-500">{t("hnrnpPanel.colBg")}</th>
                  <th className="px-3 py-2 text-center font-semibold text-muted-foreground">z</th>
                  <th className="px-3 py-2 text-center font-semibold text-muted-foreground">p (adj)</th>
                </tr>
              </thead>
              <tbody>
                {filteredResults.map((r, i) => {
                  const sigPct = r.sig_total > 0 ? ((r.sig_hit_count / r.sig_total) * 100).toFixed(1) : "0";
                  const bgPct = r.bg_total > 0 ? ((r.bg_hit_count / r.bg_total) * 100).toFixed(1) : "0";
                  return (
                    <tr
                      key={`${r.motif_name}-${r.region}-${i}`}
                      className={`border-b border-border/50 ${r.significant ? "bg-green-50/50 dark:bg-green-950/10" : ""}`}
                    >
                      <td className="px-3 py-1.5">
                        <span className={`inline-flex px-1.5 py-0.5 rounded text-[9px] font-semibold border ${PROTEIN_COLORS[r.protein] ?? "bg-muted text-muted-foreground border-border"}`}>
                          {r.protein}
                        </span>
                      </td>
                      <td className="px-3 py-1.5 font-mono font-bold text-foreground">{r.motif_name}</td>
                      <td className="px-3 py-1.5 text-muted-foreground">{REGION_LABELS[r.region] ?? r.region}</td>
                      <td className="px-3 py-1.5 text-center tabular-nums">
                        <span className="font-semibold text-foreground">{r.sig_hit_count}</span>
                        <span className="text-muted-foreground">/{r.sig_total}</span>
                        <span className="text-[9px] text-muted-foreground ml-1">({sigPct}%)</span>
                      </td>
                      <td className="px-3 py-1.5 text-center tabular-nums text-muted-foreground">
                        {r.bg_hit_count}/{r.bg_total}
                        <span className="text-[9px] ml-1">({bgPct}%)</span>
                      </td>
                      <td className="px-3 py-1.5 text-center tabular-nums text-muted-foreground">
                        {r.z_stat !== null ? r.z_stat.toFixed(2) : "—"}
                      </td>
                      <td className={`px-3 py-1.5 text-center tabular-nums font-semibold ${
                        r.p_adjusted !== null && r.p_adjusted < 0.01 ? "text-green-600 dark:text-green-400" :
                        r.p_adjusted !== null && r.p_adjusted < 0.05 ? "text-amber-600 dark:text-amber-400" :
                        "text-muted-foreground"
                      }`}>
                        {r.p_adjusted !== null
                          ? (r.p_adjusted < 0.0001 ? r.p_adjusted.toExponential(2) : r.p_adjusted.toFixed(4))
                          : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="px-4 py-2 border-t border-border text-[10px] text-muted-foreground flex items-center gap-4">
            <span>{t("hnrnpPanel.showing", { n: filteredResults.length, total: data.results.length })}</span>
            <span className="ml-auto italic">{t("hnrnpPanel.bonferroni")}</span>
          </div>
        </div>
      )}

      {/* Heatmap: protein × region */}
      <HeatmapView data={data} />

      <ScienceNote
        title={t("scienceNotes.hnrnpMotifs.title")}
        body={t("scienceNotes.hnrnpMotifs.body")}
        refs={["rmaps2"]}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Heatmap view: protein families × regions
// ---------------------------------------------------------------------------

function HeatmapView({ data }: { data: HnRNPMotifResponse }) {
  const t = useT();

  // Build a matrix: for each protein × region, pick the most significant motif
  const proteins = [...new Set(data.results.map((r) => r.protein))];
  const matrix: Record<string, Record<string, MotifEnrichmentItem | null>> = {};
  for (const p of proteins) {
    matrix[p] = {};
    for (const r of REGION_ORDER) {
      const candidates = data.results.filter((x) => x.protein === p && x.region === r);
      // Pick the one with lowest p_adjusted
      const best = candidates.reduce<MotifEnrichmentItem | null>((acc, c) => {
        if (acc === null) return c;
        if (c.p_adjusted !== null && (acc.p_adjusted === null || c.p_adjusted < acc.p_adjusted)) return c;
        return acc;
      }, null);
      matrix[p][r] = best;
    }
  }

  return (
    <div>
      <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-2">
        {t("hnrnpPanel.heatmapTitle")}
      </p>
      <div className="overflow-x-auto">
        <table className="text-[10px]">
          <thead>
            <tr>
              <th className="px-2 py-1 text-left text-muted-foreground"></th>
              {REGION_ORDER.map((r) => (
                <th key={r} className="px-2 py-1 text-center text-muted-foreground font-medium whitespace-nowrap">
                  {REGION_LABELS[r]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {proteins.map((p) => (
              <tr key={p}>
                <td className="px-2 py-1 font-semibold text-foreground whitespace-nowrap">{p}</td>
                {REGION_ORDER.map((r) => {
                  const item = matrix[p][r];
                  if (!item || item.p_adjusted === null) {
                    return <td key={r} className="px-2 py-1 text-center text-muted-foreground/30">—</td>;
                  }
                  const enriched = item.sig_density > item.bg_density;
                  const sig = item.p_adjusted < 0.05;
                  let bgColor = "bg-slate-100 dark:bg-slate-800";
                  if (sig && enriched) bgColor = "bg-red-200 dark:bg-red-900/40";
                  else if (sig && !enriched) bgColor = "bg-blue-200 dark:bg-blue-900/40";
                  return (
                    <td
                      key={r}
                      className={`px-2 py-1 text-center rounded ${bgColor}`}
                      title={`${item.motif_name}: p_adj=${item.p_adjusted.toFixed(4)}, z=${item.z_stat?.toFixed(2)}`}
                    >
                      <span className={`font-mono font-bold ${sig ? "text-foreground" : "text-muted-foreground"}`}>
                        {item.motif_name}
                      </span>
                      {sig && (
                        <span className="ml-0.5 text-[8px]">*</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center gap-3 mt-1.5 text-[9px] text-muted-foreground">
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-2 rounded bg-red-200 dark:bg-red-900/40" /> {t("hnrnpPanel.enriched")}</span>
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-2 rounded bg-blue-200 dark:bg-blue-900/40" /> {t("hnrnpPanel.depleted")}</span>
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-2 rounded bg-slate-100 dark:bg-slate-800" /> n.s.</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function SummaryChip({ label, value, highlight }: { label: string; value: number; highlight?: boolean }) {
  return (
    <div className={`text-center px-3 py-2 rounded-lg border ${
      highlight
        ? "bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800"
        : "bg-muted/40 border-border"
    }`}>
      <p className={`text-[9px] uppercase tracking-wide font-semibold ${highlight ? "text-green-700 dark:text-green-400" : "text-muted-foreground"}`}>
        {label}
      </p>
      <p className={`text-base font-bold tabular-nums ${highlight ? "text-green-700 dark:text-green-300" : "text-foreground"}`}>
        {value}
      </p>
    </div>
  );
}
