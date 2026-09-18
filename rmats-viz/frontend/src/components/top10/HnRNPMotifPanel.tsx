"use client";

/**
 * HnRNPMotifPanel
 * ================
 * Displays hnRNP motif enrichment analysis results: known RNA-binding
 * protein motifs in significant vs background events, across seven genomic
 * regions around skipped exons (rMAPS2 design, E1):
 *
 *   upstream exon · upstream intron (5′ss side) · upstream intron (3′ss side)
 *   · skipped exon · downstream intron (5′ss side) · downstream intron (3′ss side)
 *   · downstream exon
 *
 * Two tests per (motif × region) pair (E2):
 *   • presence — two-proportion z-test on motif presence (q = p_adjusted)
 *   • density  — Mann-Whitney U on per-event motif density (q = density_p_adjusted)
 * A pair is flagged significant when EITHER test passes the BH threshold.
 *
 * Inspired by rMAPS2 (Hwang et al., NAR 2020).
 *
 * Data: GET /api/v1/deep-analyses/{id}/hnrnp-motifs
 */

import { useQuery } from "@tanstack/react-query";
import { Fragment, useState, useMemo } from "react";
import { fetchJSON, BASE } from "@/lib/api/client";
import { ScienceNote } from "@/components/ScienceNote";
import { useT } from "@/contexts/LanguageContext";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface MotifEnrichmentItem {
  motif_name: string;
  protein: string;
  /** One of REGION_ORDER */
  region: string;
  sig_hit_count: number;
  sig_total: number;
  bg_hit_count: number;
  bg_total: number;
  sig_density: number;
  bg_density: number;
  // Presence test (two-proportion z)
  z_stat: number | null;
  p_value: number | null;
  p_adjusted: number | null;
  significant: boolean;
  // Density test (Mann-Whitney U)
  density_u_stat: number | null;
  density_p_value: number | null;
  density_p_adjusted: number | null;
  density_significant: boolean;
  regulatory_effect: string | null; // ESE/ESS/ISE/ISS or null
}

export interface HnRNPMotifResponse {
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

export const REGION_ORDER = [
  "upstream_exon",
  "upstream_intron_5ss",
  "upstream_intron_3ss",
  "skipped_exon",
  "downstream_intron_5ss",
  "downstream_intron_3ss",
  "downstream_exon",
] as const;

type T = ReturnType<typeof useT>;

/** i18n region label with a graceful fallback to the raw region key. */
function regionLabel(t: T, region: string): string {
  const key = `hnrnpPanel.regions.${region}`;
  const label = t(key);
  return label === key ? region : label;
}

/** Smallest of the two adjusted p-values (null when neither is available). */
function minQ(r: MotifEnrichmentItem): number | null {
  const qs = [r.p_adjusted, r.density_p_adjusted].filter((q): q is number => q != null);
  return qs.length ? Math.min(...qs) : null;
}

/** Significant if either the presence or the density test passes. */
function isSig(r: MotifEnrichmentItem): boolean {
  return r.significant || r.density_significant;
}

function fmtQ(q: number | null): string {
  if (q === null) return "—";
  return q < 0.0001 ? q.toExponential(2) : q.toFixed(4);
}

function qColorClass(q: number | null): string {
  if (q !== null && q < 0.01) return "text-green-600 dark:text-green-400";
  if (q !== null && q < 0.05) return "text-amber-600 dark:text-amber-400";
  return "text-muted-foreground";
}

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

// Regulatory effect inset border colors for heatmap cells
// Uses inset box-shadow so the frame stays inside the cell (no overlap)
// Silencers (ESS/ISS) = orange-600 frame, Enhancers (ESE/ISE) = emerald-600 frame
const EFFECT_BORDER: Record<string, string> = {
  ESS: "shadow-[inset_0_0_0_2px_#ea580c]",
  ISS: "shadow-[inset_0_0_0_2px_#ea580c]",
  ESE: "shadow-[inset_0_0_0_2px_#059669]",
  ISE: "shadow-[inset_0_0_0_2px_#059669]",
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
    return Array.from(new Set(data.results.map((r) => r.protein)));
  }, [data]);

  // Regions actually present in the data (REGION_ORDER first, then any unknown)
  const regions = useMemo<string[]>(() => {
    if (!data) return [...REGION_ORDER];
    const present = new Set(data.results.map((r) => r.region));
    const known = REGION_ORDER.filter((r) => present.has(r));
    const unknown = Array.from(present).filter((r) => !(REGION_ORDER as readonly string[]).includes(r));
    return known.length || unknown.length ? [...known, ...unknown] : [...REGION_ORDER];
  }, [data]);

  // Filter & sort results
  const filteredResults = useMemo(() => {
    if (!data) return [];
    let results = data.results;
    if (!showAll) {
      results = results.filter(isSig);
    }
    if (selectedProtein) {
      results = results.filter((r) => r.protein === selectedProtein);
    }
    if (selectedRegion) {
      results = results.filter((r) => r.region === selectedRegion);
    }
    // Sort by the smaller of the two q-values (most significant first)
    return [...results].sort((a, b) => {
      const qa = minQ(a);
      const qb = minQ(b);
      if (qa === null) return 1;
      if (qb === null) return -1;
      return qa - qb;
    });
  }, [data, showAll, selectedProtein, selectedRegion]);

  // Significant count (either test)
  const nSignificant = useMemo(
    () => data?.results.filter(isSig).length ?? 0,
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
          {regions.map((r) => (
            <option key={r} value={r}>{regionLabel(t, r)}</option>
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
                  <th className="px-3 py-2 text-center font-semibold text-muted-foreground" title={t("hnrnpPanel.presenceTooltip")}>
                    {t("hnrnpPanel.colPresenceQ")}
                  </th>
                  <th className="px-3 py-2 text-center font-semibold text-muted-foreground" title={t("hnrnpPanel.densityTooltip")}>
                    {t("hnrnpPanel.colDensityQ")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {filteredResults.map((r, i) => {
                  const sigPct = r.sig_total > 0 ? ((r.sig_hit_count / r.sig_total) * 100).toFixed(1) : "0";
                  const bgPct = r.bg_total > 0 ? ((r.bg_hit_count / r.bg_total) * 100).toFixed(1) : "0";
                  const sig = isSig(r);
                  return (
                    <tr
                      key={`${r.motif_name}-${r.region}-${i}`}
                      className={`border-b border-border/50 ${sig ? "bg-green-50/50 dark:bg-green-950/10" : ""}`}
                    >
                      <td className="px-3 py-1.5">
                        <span className={`inline-flex px-1.5 py-0.5 rounded text-[9px] font-semibold border ${PROTEIN_COLORS[r.protein] ?? "bg-muted text-muted-foreground border-border"}`}>
                          {r.protein}
                        </span>
                      </td>
                      <td className="px-3 py-1.5 font-mono font-bold text-foreground">{r.motif_name}</td>
                      <td className="px-3 py-1.5 text-muted-foreground">{regionLabel(t, r.region)}</td>
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
                      <td className={`px-3 py-1.5 text-center tabular-nums font-semibold ${qColorClass(r.p_adjusted)}`}>
                        {fmtQ(r.p_adjusted)}{r.significant ? "*" : ""}
                      </td>
                      <td
                        className={`px-3 py-1.5 text-center tabular-nums font-semibold ${qColorClass(r.density_p_adjusted)}`}
                        title={r.density_u_stat !== null ? `U = ${r.density_u_stat.toFixed(1)} · ${r.sig_density.toFixed(3)} vs ${r.bg_density.toFixed(3)}` : undefined}
                      >
                        {fmtQ(r.density_p_adjusted)}{r.density_significant ? "*" : ""}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="px-4 py-2 border-t border-border text-[10px] text-muted-foreground flex flex-wrap items-center gap-4">
            <span>{t("hnrnpPanel.showing", { n: filteredResults.length, total: data.results.length })}</span>
            <span className="ml-auto italic">{t("hnrnpPanel.bonferroni")}</span>
          </div>
        </div>
      )}

      {/* Heatmap: protein × region */}
      <HeatmapView data={data} regions={regions} />

      <ScienceNote
        title={t("scienceNotes.hnrnpMotifs.title")}
        body={t("scienceNotes.hnrnpMotifs.body")}
        refs={["rmaps2", "cisbp_rna"]}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Heatmap view: protein families × regions
// ---------------------------------------------------------------------------

function HeatmapView({ data, regions }: { data: HnRNPMotifResponse; regions: string[] }) {
  const t = useT();

  // Build a matrix: for each protein × region, pick the most significant motif
  // (smallest of the presence / density q-values).
  const proteins = Array.from(new Set(data.results.map((r) => r.protein)));
  const matrix: Record<string, Record<string, MotifEnrichmentItem | null>> = {};
  for (const p of proteins) {
    matrix[p] = {};
    for (const r of regions) {
      const candidates = data.results.filter((x) => x.protein === p && x.region === r);
      const best = candidates.reduce<MotifEnrichmentItem | null>((acc, c) => {
        if (acc === null) return c;
        const qc = minQ(c);
        const qa = minQ(acc);
        if (qc !== null && (qa === null || qc < qa)) return c;
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
        {/* CSS grid layout matching the PDF vector heatmap style */}
        <div
          className="inline-grid gap-px bg-slate-200 dark:bg-slate-700 border border-slate-200 dark:border-slate-700"
          style={{
            gridTemplateColumns: `minmax(100px, auto) repeat(${regions.length}, minmax(72px, 1fr))`,
          }}
        >
          {/* Header row */}
          <div className="bg-white dark:bg-background" />
          {regions.map((r) => (
            <div
              key={r}
              className="bg-white dark:bg-background px-2 py-1.5 text-center text-[9px] font-bold text-slate-600 dark:text-slate-400 leading-tight"
            >
              {regionLabel(t, r)}
            </div>
          ))}

          {/* Data rows */}
          {proteins.map((p) => (
            <Fragment key={p}>
              {/* Protein label */}
              <div
                className="bg-white dark:bg-background px-3 py-1 flex items-center text-[10px] font-bold text-foreground whitespace-nowrap"
              >
                {p}
              </div>
              {/* Region cells */}
              {regions.map((r) => {
                const item = matrix[p][r];
                const q = item ? minQ(item) : null;
                if (!item || q === null) {
                  return (
                    <div
                      key={`${p}-${r}`}
                      className="bg-slate-50 dark:bg-slate-800/60 flex items-center justify-center min-h-[32px] text-[10px] text-muted-foreground/30"
                    >
                      —
                    </div>
                  );
                }
                const enriched = item.sig_density > item.bg_density;
                const sig = isSig(item) || q < 0.05;
                let bgColor = "bg-slate-100 dark:bg-slate-800";
                if (sig && enriched) bgColor = "bg-red-200 dark:bg-red-900/40";
                else if (sig && !enriched) bgColor = "bg-blue-200 dark:bg-blue-900/40";
                const effectRing = item.regulatory_effect ? (EFFECT_BORDER[item.regulatory_effect] ?? "") : "";
                const effectLabel = item.regulatory_effect ?? "";
                const title = [
                  item.motif_name,
                  `${t("hnrnpPanel.colPresenceQ")}=${fmtQ(item.p_adjusted)}${item.z_stat != null ? ` (z=${item.z_stat.toFixed(2)})` : ""}`,
                  `${t("hnrnpPanel.colDensityQ")}=${fmtQ(item.density_p_adjusted)}${item.density_u_stat != null ? ` (U=${item.density_u_stat.toFixed(1)})` : ""}`,
                  effectLabel ? `(${effectLabel})` : "",
                ].filter(Boolean).join(" · ");
                return (
                  <div
                    key={`${p}-${r}`}
                    className={`flex flex-col items-center justify-center min-h-[32px] px-1 py-0.5 ${bgColor} ${effectRing}`}
                    title={title}
                  >
                    <span className={`font-mono font-bold text-[10px] leading-tight ${sig ? "text-foreground" : "text-muted-foreground"}`}>
                      {item.motif_name}{sig ? "*" : ""}
                    </span>
                    {effectLabel && (
                      <span className={`text-[7px] font-bold leading-none mt-0.5 ${
                        effectLabel === "ESS" || effectLabel === "ISS"
                          ? "text-orange-600 dark:text-orange-400"
                          : "text-emerald-600 dark:text-emerald-400"
                      }`}>
                        {effectLabel}
                      </span>
                    )}
                  </div>
                );
              })}
            </Fragment>
          ))}
        </div>
      </div>
      {/* Legend */}
      <div className="flex flex-wrap items-center gap-3 mt-2 text-[9px] text-muted-foreground">
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-2 bg-red-200 dark:bg-red-900/40" /> {t("hnrnpPanel.enriched")}</span>
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-2 bg-blue-200 dark:bg-blue-900/40" /> {t("hnrnpPanel.depleted")}</span>
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-2 bg-slate-100 dark:bg-slate-800" /> n.s.</span>
        <span className="ml-1 border-l border-border pl-2" />
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-2 shadow-[inset_0_0_0_2px_#ea580c] bg-white dark:bg-slate-800" /> {t("hnrnpPanel.silencer")}</span>
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-2 shadow-[inset_0_0_0_2px_#059669] bg-white dark:bg-slate-800" /> {t("hnrnpPanel.enhancer")}</span>
      </div>
      <p className="mt-1 text-[9px] text-muted-foreground italic">{t("hnrnpPanel.heatmapNote")}</p>
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
