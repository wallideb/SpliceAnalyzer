"use client";

/**
 * PermutationPanel
 * =================
 * Visualisation du test de permutation patients/contrôles.
 *
 * Onglets disponibles :
 *  • ΔΨ         — distribution nulle vs observée (test par événement)
 *  • Score PPT  — permutation sur le score polypyrimidique moyen
 *  • Taille exon — permutation sur la taille normalisée de l'exon sauté
 *  • Phase/cadre — permutation sur la fraction in-frame
 *  • Sites consensus — permutation sur le score GT-AG canonique
 *
 * Méthode : test de permutation bilatéral H₀ — p = (k+1)/(N+1).
 */

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { runPermutationTest } from "@/lib/api/splice";
import { useT } from "@/contexts/LanguageContext";
import type { MetricPermResult, PermutationResponse } from "@/types/splice";

// ---------------------------------------------------------------------------
// Tab definitions
// ---------------------------------------------------------------------------

type TabId = "delta_psi" | "ppt_score" | "exon_size" | "frame_in_frame" | "canonical_sites";

interface TabDef {
  id: TabId;
  labelKey: string;
  metricName?: string;  // matches MetricPermResult.metric_name; undefined = ΔΨ tab
  descKey: string;
}

const TABS: TabDef[] = [
  {
    id: "delta_psi",
    labelKey: "permutation.tabs.delta_psi.label",
    descKey: "permutation.tabs.delta_psi.description",
  },
  {
    id: "ppt_score",
    metricName: "ppt_score",
    labelKey: "permutation.tabs.ppt_score.label",
    descKey: "permutation.tabs.ppt_score.description",
  },
  {
    id: "exon_size",
    metricName: "exon_size",
    labelKey: "permutation.tabs.exon_size.label",
    descKey: "permutation.tabs.exon_size.description",
  },
  {
    id: "frame_in_frame",
    metricName: "frame_in_frame",
    labelKey: "permutation.tabs.frame_in_frame.label",
    descKey: "permutation.tabs.frame_in_frame.description",
  },
  {
    id: "canonical_sites",
    metricName: "canonical_sites",
    labelKey: "permutation.tabs.canonical_sites.label",
    descKey: "permutation.tabs.canonical_sites.description",
  },
];

// ---------------------------------------------------------------------------
// ΔΨ Dual-histogram SVG
// ---------------------------------------------------------------------------

interface DualHistProps {
  nullBins: number[];
  nullCounts: number[];
  obsBins: number[];
  obsCounts: number[];
}

function DualHistogram({ nullBins, nullCounts, obsBins, obsCounts }: DualHistProps) {
  if (!nullBins.length) return null;

  const W = 500;
  const MARGIN_T = 18;
  const CHART_H = 110;
  const MARGIN_B = 24;
  const SVG_H = MARGIN_T + CHART_H + MARGIN_B;

  const maxCount = Math.max(...nullCounts, ...obsCounts, 1);
  const n = nullBins.length;
  const barW = Math.max(3, Math.floor(W / n) - 1);

  return (
    <div style={{ overflowX: "auto" }}>
      <svg
        viewBox={`0 0 ${W} ${SVG_H}`}
        style={{ width: W, height: SVG_H, display: "block" }}
        aria-label="Distribution des ΔΨ sous H₀ (permutation)"
      >
        {nullBins.map((bin, i) => {
          const nullH  = Math.round((nullCounts[i]  / maxCount) * CHART_H);
          const obsH   = Math.round(((obsCounts[i] ?? 0) / maxCount) * CHART_H);
          const x = i * (barW + 1);
          return (
            <g key={i}>
              <title>{`ΔΨ ≈ ${bin.toFixed(2)} — H₀: ${nullCounts[i]}, observé: ${obsCounts[i] ?? 0}`}</title>
              <rect
                x={x} y={MARGIN_T + CHART_H - nullH}
                width={barW} height={nullH}
                fill="#3b82f6" opacity={0.45}
              />
              {(obsCounts[i] ?? 0) > 0 && (
                <rect
                  x={x} y={MARGIN_T + CHART_H - obsH}
                  width={barW} height={obsH}
                  fill="#f97316" opacity={0.7}
                />
              )}
              {i % 5 === 0 && (
                <text
                  x={x + barW / 2} y={MARGIN_T + CHART_H + 12}
                  textAnchor="middle" fontSize={6.5}
                  fontFamily="monospace" fill="#94a3b8"
                >
                  {bin.toFixed(1)}
                </text>
              )}
            </g>
          );
        })}
        <line x1={0} y1={MARGIN_T + CHART_H} x2={W} y2={MARGIN_T + CHART_H} stroke="#334155" strokeWidth={0.5} />
        <text x={2} y={MARGIN_T - 3} fontSize={6.5} fill="#64748b" fontFamily="sans-serif">N</text>
        <text x={W} y={SVG_H - 2} textAnchor="end" fontSize={6.5} fill="#64748b" fontFamily="sans-serif" fontStyle="italic">ΔΨ</text>
      </svg>
      <DualHistLegend />
    </div>
  );
}

function DualHistLegend() {
  const t = useT();
  return (
    <div className="flex items-center gap-4 text-[9px] text-muted-foreground mt-1">
      <span className="flex items-center gap-1">
        <span className="inline-block w-4 h-2.5 rounded-sm bg-blue-500/45" />
        {t("permutation.results.nullDistribution")} (permutations)
      </span>
      <span className="flex items-center gap-1">
        <span className="inline-block w-4 h-2.5 rounded-sm bg-orange-500/70" />
        ΔΨ {t("permutation.results.observedDeltaPsi").toLowerCase()}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Metric histogram SVG (null distribution + observed stat vertical line)
// ---------------------------------------------------------------------------

function MetricHistogram({ metric }: { metric: MetricPermResult }) {
  if (!metric.null_hist_bins.length) {
    return (
      <p className="text-[9px] text-muted-foreground italic py-4 text-center">
        Données insuffisantes pour ce paramètre (n={metric.n_valid} événements avec valeur).
      </p>
    );
  }

  const W = 500;
  const MARGIN_T = 18;
  const CHART_H = 110;
  const MARGIN_B = 24;
  const SVG_H = MARGIN_T + CHART_H + MARGIN_B;
  const maxCount = Math.max(...metric.null_hist_counts, 1);
  const n = metric.null_hist_bins.length;
  const barW = Math.max(3, Math.floor(W / n) - 1);

  // Position of observed_stat vertical line
  let obsLineX: number | null = null;
  if (metric.observed_stat !== null && metric.null_hist_bins.length > 1) {
    const lo = metric.null_hist_bins[0];
    const hi = metric.null_hist_bins[metric.null_hist_bins.length - 1];
    const range = hi - lo || 1;
    obsLineX = Math.max(0, Math.min(W, ((metric.observed_stat - lo) / range) * W));
  }

  const sig = metric.empirical_p_value !== null && metric.empirical_p_value < 0.05;
  const obsColor = sig ? "#22c55e" : "#f97316";

  return (
    <div style={{ overflowX: "auto" }}>
      <svg
        viewBox={`0 0 ${W} ${SVG_H}`}
        style={{ width: W, height: SVG_H, display: "block" }}
        aria-label={`Distribution nulle — ${metric.label}`}
      >
        {metric.null_hist_bins.map((bin, i) => {
          const h = Math.round((metric.null_hist_counts[i] / maxCount) * CHART_H);
          const x = i * (barW + 1);
          return (
            <g key={i}>
              <title>{`${metric.label} ≈ ${bin.toFixed(3)} — H₀: ${metric.null_hist_counts[i]}`}</title>
              <rect
                x={x} y={MARGIN_T + CHART_H - h}
                width={barW} height={h}
                fill="#3b82f6" opacity={0.5}
              />
              {i % 5 === 0 && (
                <text
                  x={x + barW / 2} y={MARGIN_T + CHART_H + 12}
                  textAnchor="middle" fontSize={6.5}
                  fontFamily="monospace" fill="#94a3b8"
                >
                  {bin.toFixed(2)}
                </text>
              )}
            </g>
          );
        })}
        {/* Observed stat vertical line */}
        {obsLineX !== null && (
          <g>
            <line
              x1={obsLineX} y1={MARGIN_T}
              x2={obsLineX} y2={MARGIN_T + CHART_H}
              stroke={obsColor} strokeWidth={2} strokeDasharray="4 2"
            />
            <text
              x={obsLineX + 3} y={MARGIN_T + 10}
              fontSize={7} fill={obsColor} fontFamily="monospace" fontWeight="bold"
            >
              {metric.observed_stat !== null
                ? (metric.observed_stat >= 0 ? "+" : "") + metric.observed_stat.toFixed(3)
                : ""}
            </text>
          </g>
        )}
        <line x1={0} y1={MARGIN_T + CHART_H} x2={W} y2={MARGIN_T + CHART_H} stroke="#334155" strokeWidth={0.5} />
        <text x={2} y={MARGIN_T - 3} fontSize={6.5} fill="#64748b" fontFamily="sans-serif">N</text>
      </svg>
      <MetricHistLegend obsColor={obsColor} observedStat={metric.observed_stat} />
    </div>
  );
}

function MetricHistLegend({ obsColor, observedStat }: { obsColor: string; observedStat: number | null }) {
  const t = useT();
  return (
    <div className="flex items-center gap-4 text-[9px] text-muted-foreground mt-1">
      <span className="flex items-center gap-1">
        <span className="inline-block w-4 h-2.5 rounded-sm bg-blue-500/50" />
        {t("permutation.results.nullDistribution")} H₀
      </span>
      <span className="flex items-center gap-1">
        <span className="inline-block w-4 h-0.5 rounded-sm" style={{ backgroundColor: obsColor }} />
        {t("permutation.results.observedDelta")}
        {observedStat !== null && (
          <span className="tabular-nums font-mono">
            {" "}({observedStat >= 0 ? "+" : ""}{observedStat.toFixed(3)})
          </span>
        )}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Metric summary chips
// ---------------------------------------------------------------------------

function MetricSummary({ metric }: { metric: MetricPermResult }) {
  const t = useT();
  const p = metric.empirical_p_value;
  const sig01 = p !== null && p < 0.01;
  const sig05 = p !== null && p < 0.05;
  return (
    <div className="flex flex-wrap gap-3">
      <div className="text-center px-3 py-2 rounded-lg bg-muted/40 border border-border">
        <p className="text-[9px] text-muted-foreground uppercase tracking-wide">{t("permutation.results.validEvents")}</p>
        <p className="text-base font-bold tabular-nums">{metric.n_valid}</p>
      </div>
      <div className="text-center px-3 py-2 rounded-lg bg-muted/40 border border-border">
        <p className="text-[9px] text-muted-foreground uppercase tracking-wide">{t("permutation.results.g1")}</p>
        <p className="text-sm font-bold tabular-nums text-blue-600 dark:text-blue-400">{metric.n_g1}</p>
      </div>
      <div className="text-center px-3 py-2 rounded-lg bg-muted/40 border border-border">
        <p className="text-[9px] text-muted-foreground uppercase tracking-wide">{t("permutation.results.g2")}</p>
        <p className="text-sm font-bold tabular-nums text-red-600 dark:text-red-400">{metric.n_g2}</p>
      </div>
      {metric.observed_stat !== null && (
        <div className="text-center px-3 py-2 rounded-lg bg-muted/40 border border-border">
          <p className="text-[9px] text-muted-foreground uppercase tracking-wide">{t("permutation.results.observedDelta")}</p>
          <p className="text-sm font-bold tabular-nums font-mono">
            {metric.observed_stat >= 0 ? "+" : ""}{metric.observed_stat.toFixed(3)}
          </p>
        </div>
      )}
      {p !== null && (
        <div className={`text-center px-3 py-2 rounded-lg border ${
          sig01 ? "bg-green-50 border-green-200 dark:bg-green-950/20 dark:border-green-700" :
          sig05 ? "bg-amber-50 border-amber-200 dark:bg-amber-950/20 dark:border-amber-700" :
                  "bg-muted/40 border-border"
        }`}>
          <p className="text-[9px] text-muted-foreground uppercase tracking-wide">{t("permutation.results.empiricalP")}</p>
          <p className={`text-sm font-bold tabular-nums ${
            sig01 ? "text-green-700 dark:text-green-400" :
            sig05 ? "text-amber-700 dark:text-amber-400" : ""
          }`}>
            {p.toFixed(3)}
          </p>
          {(sig01 || sig05) && (
            <p className={`text-[8px] font-bold ${sig01 ? "text-green-600 dark:text-green-400" : "text-amber-600 dark:text-amber-400"}`}>
              {sig01 ? "★ p<0.01" : "✓ p<0.05"}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Top-events table (ΔΨ tab only)
// ---------------------------------------------------------------------------

function TopEventsTable({ events }: { events: PermutationResponse["events"] }) {
  const t = useT();
  const sorted = [...events]
    .filter((e) => e.empirical_p_value !== null)
    .sort((a, b) => (a.empirical_p_value ?? 1) - (b.empirical_p_value ?? 1))
    .slice(0, 15);

  if (!sorted.length) return null;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[10px] border-collapse">
        <thead>
          <tr className="bg-muted/50">
            <th className="text-left px-2 py-1.5 font-semibold text-muted-foreground border border-border">{t("permutation.results.gene")}</th>
            <th className="text-right px-2 py-1.5 font-semibold text-muted-foreground border border-border">{t("permutation.results.observedDeltaPsi")}</th>
            <th className="text-right px-2 py-1.5 font-semibold text-muted-foreground border border-border">{t("permutation.results.empiricalPValue")}</th>
            <th className="text-left px-2 py-1.5 font-semibold text-muted-foreground border border-border">{t("permutation.results.nGroups")}</th>
            <th className="text-left px-2 py-1.5 font-semibold text-muted-foreground border border-border">{t("permutation.results.significant")}</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((ev) => {
            const p = ev.empirical_p_value ?? 1;
            const sig05 = p < 0.05;
            const sig01 = p < 0.01;
            return (
              <tr key={ev.event_id} className="hover:bg-muted/30 transition-colors">
                <td className="px-2 py-1 border border-border font-mono font-semibold text-foreground">
                  {ev.gene_symbol ?? "—"}
                </td>
                <td className="px-2 py-1 border border-border text-right tabular-nums">
                  {ev.observed_delta_psi !== null
                    ? (ev.observed_delta_psi >= 0 ? "+" : "") + ev.observed_delta_psi.toFixed(3)
                    : "—"}
                </td>
                <td className={`px-2 py-1 border border-border text-right tabular-nums font-semibold ${
                  sig01 ? "text-green-600 dark:text-green-400" :
                  sig05 ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground"
                }`}>
                  {p.toFixed(3)}
                </td>
                <td className="px-2 py-1 border border-border text-muted-foreground">
                  {ev.n1} / {ev.n2}
                </td>
                <td className="px-2 py-1 border border-border">
                  {sig01 ? (
                    <span className="text-green-600 dark:text-green-400 font-bold">✓ p&lt;0.01</span>
                  ) : sig05 ? (
                    <span className="text-amber-600 dark:text-amber-400 font-bold">✓ p&lt;0.05</span>
                  ) : (
                    <span className="text-muted-foreground">ns</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Method description line (shown below every histogram)
// ---------------------------------------------------------------------------

function MethodLine() {
  const t = useT();
  return (
    <p className="text-[9px] text-muted-foreground italic mt-1 leading-relaxed">
      {t("permutation.results.method")}
    </p>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function PermutationPanel({ analysisId }: { analysisId: string }) {
  const t = useT();
  const [nIterations, setNIterations] = useState(500);
  const [result, setResult] = useState<PermutationResponse | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>("delta_psi");

  const { mutate, isPending, isError } = useMutation({
    mutationFn: () => runPermutationTest(analysisId, nIterations),
    onSuccess: (data) => setResult(data),
  });

  return (
    <div className="space-y-5 text-xs">

      {/* ── Header + controls ── */}
      <div className="flex flex-wrap items-end gap-4">
        <div>
          <label className="block text-[9px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">
            {t("permutation.iterations")}
          </label>
          <div className="flex items-center gap-2">
            <input
              type="range"
              min={50}
              max={2000}
              step={50}
              value={nIterations}
              onChange={(e) => setNIterations(Number(e.target.value))}
              className="w-32 accent-blue-600"
            />
            <span className="text-sm font-bold tabular-nums text-foreground w-10 text-right">
              {nIterations}
            </span>
          </div>
          <p className="text-[9px] text-muted-foreground mt-0.5">
            {t("permutation.moreIterations")}
          </p>
        </div>

        <button
          onClick={() => mutate()}
          disabled={isPending}
          className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg disabled:opacity-50 transition-colors"
        >
          {isPending && (
            <svg className="animate-spin w-3.5 h-3.5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          )}
          {isPending ? t("permutation.running", { n: String(nIterations) }) : t("permutation.launch")}
        </button>
      </div>

      {isError && (
        <p className="text-xs text-red-500">
          {t("permutation.error")}
        </p>
      )}

      {/* ── Results ── */}
      {result && (
        <div className="space-y-4">

          {/* Summary badges — always from ΔΨ test */}
          <div className="flex flex-wrap gap-3">
            <div className="text-center px-3 py-2 rounded-lg bg-muted/40 border border-border">
              <p className="text-[9px] text-muted-foreground uppercase tracking-wide">{t("permutation.results.eventsTested")}</p>
              <p className="text-base font-bold tabular-nums">{result.n_events_tested}</p>
            </div>
            <div className="text-center px-3 py-2 rounded-lg bg-muted/40 border border-border">
              <p className="text-[9px] text-muted-foreground uppercase tracking-wide">{t("permutation.results.iterations")}</p>
              <p className="text-base font-bold tabular-nums">{result.n_iterations}</p>
            </div>
            {result.pct_p05 !== null && (
              <div className="text-center px-3 py-2 rounded-lg bg-amber-50 border border-amber-200 dark:bg-amber-950/20 dark:border-amber-700">
                <p className="text-[9px] text-muted-foreground uppercase tracking-wide">{t("permutation.results.sig05")}</p>
                <p className="text-base font-bold tabular-nums text-amber-700 dark:text-amber-400">
                  {result.pct_p05}%
                </p>
              </div>
            )}
            {result.pct_p01 !== null && (
              <div className="text-center px-3 py-2 rounded-lg bg-green-50 border border-green-200 dark:bg-green-950/20 dark:border-green-700">
                <p className="text-[9px] text-muted-foreground uppercase tracking-wide">{t("permutation.results.sig01")}</p>
                <p className="text-base font-bold tabular-nums text-green-700 dark:text-green-400">
                  {result.pct_p01}%
                </p>
              </div>
            )}
          </div>

          {/* ── Horizontal tab bar ── */}
          <div className="border-b border-border">
            <nav className="flex gap-1 -mb-px overflow-x-auto" aria-label={t("permutation.iterations")}>
              {TABS.map((tab) => {
                const active = activeTab === tab.id;
                // Check if this metric has data (if it's a metric tab)
                const hasData = !tab.metricName || result.metric_results.some(m => m.metric_name === tab.metricName);
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    disabled={!hasData}
                    className={`px-3 py-2 text-[10px] font-semibold whitespace-nowrap border-b-2 transition-colors disabled:opacity-40 ${
                      active
                        ? "border-indigo-500 text-indigo-600 dark:text-indigo-400"
                        : "border-transparent text-muted-foreground hover:text-foreground hover:border-muted"
                    }`}
                  >
                    {t(tab.labelKey)}
                  </button>
                );
              })}
            </nav>
          </div>

          {/* ── Tab content ── */}
          <div className="space-y-4">
            {/* Tab description */}
            <p className="text-[9px] text-muted-foreground">
              {TABS.find(tab => tab.id === activeTab)?.descKey ? t(TABS.find(tab => tab.id === activeTab)!.descKey) : ""}
            </p>

            {/* ΔΨ tab */}
            {activeTab === "delta_psi" && (
              <>
                <div>
                  <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                    {t("permutation.results.nullDistribution")}
                  </p>
                  <DualHistogram
                    nullBins={result.global_null_hist_bins}
                    nullCounts={result.global_null_hist_counts}
                    obsBins={result.observed_hist_bins}
                    obsCounts={result.observed_hist_counts}
                  />
                  <MethodLine />
                </div>

                <div
                  className="p-3 rounded-lg bg-muted/30 border border-border text-[9px] leading-relaxed text-muted-foreground"
                  dangerouslySetInnerHTML={{ __html: t("permutation.results.interpretation") }}
                />

                <div>
                  <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                    {t("permutation.results.topEvents")}
                  </p>
                  <TopEventsTable events={result.events} />
                </div>
              </>
            )}

            {/* Metric tabs */}
            {activeTab !== "delta_psi" && (() => {
              const activeTabDef = TABS.find(tab => tab.id === activeTab)!;
              const metric = result.metric_results.find(m => m.metric_name === activeTabDef.metricName);
              if (!metric) {
                return (
                  <p className="text-[9px] text-muted-foreground italic py-4 text-center">
                    {t("permutation.results.requiresPermutation")}
                  </p>
                );
              }
              return (
                <>
                  <MetricSummary metric={metric} />
                  <div>
                    <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                      {t("permutation.results.nullDistLabel", { label: metric.label })}
                    </p>
                    <MetricHistogram metric={metric} />
                    <MethodLine />
                  </div>
                  <div
                    className="p-3 rounded-lg bg-muted/30 border border-border text-[9px] leading-relaxed text-muted-foreground"
                    dangerouslySetInnerHTML={{ __html: t("permutation.results.interpretationMetric") }}
                  />
                </>
              );
            })()}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!result && !isPending && (
        <div className="py-8 text-center text-muted-foreground">
          <p className="text-sm">{t("permutation.empty.main")}</p>
          <p className="text-[10px] mt-1">{t("permutation.empty.params")}</p>
        </div>
      )}
    </div>
  );
}
