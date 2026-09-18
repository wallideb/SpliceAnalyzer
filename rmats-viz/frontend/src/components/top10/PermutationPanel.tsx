"use client";

/**
 * PermutationPanel
 * =================
 * PSI permutation test: shuffles patient/control labels and recomputes ΔΨ.
 * Shows null distribution vs observed, top events table, and significance %.
 */

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { runPermutationTest } from "@/lib/api/splice";
import { useT } from "@/contexts/LanguageContext";
import { ScienceNote } from "@/components/ScienceNote";
import type { PermutationResponse, MetricPermResult } from "@/types/splice";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Binomial coefficient C(n, k) — number of distinct label splits. */
function binom(n: number, k: number): number {
  if (k < 0 || k > n) return 0;
  k = Math.min(k, n - k);
  let r = 1;
  for (let i = 1; i <= k; i++) r = (r * (n - k + i)) / i;
  return Math.round(r);
}

function fmtP(v: number | null): string {
  if (v === null) return "—";
  return v < 0.001 ? v.toExponential(2) : v.toFixed(3);
}

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
  const t = useT();
  if (!nullBins.length) return null;

  const MARGIN_L = 38;   // left Y-axis space
  const MARGIN_R = 42;   // right Y-axis space
  const W = 540;
  const CHART_W = W - MARGIN_L - MARGIN_R;
  const MARGIN_T = 18;
  const CHART_H = 110;
  const MARGIN_B = 24;
  const SVG_H = MARGIN_T + CHART_H + MARGIN_B;

  const maxNullCount = Math.max(...nullCounts, 1);
  const maxObsCount = Math.max(...obsCounts, 1);
  const n = nullBins.length;
  const barW = Math.max(3, Math.floor(CHART_W / n) - 1);

  // Y-axis tick helpers
  const nullTicks = _niceTicks(maxNullCount, 4);
  const obsTicks = _niceTicks(maxObsCount, 4);

  // Build outline polyline points connecting tops of orange dashed lines
  const outlinePoints: string[] = [];
  obsBins.forEach((_, i) => {
    const c = obsCounts[i] ?? 0;
    if (c <= 0) return;
    const x = MARGIN_L + i * (barW + 1) + barW / 2;
    const h = Math.round((c / maxObsCount) * CHART_H);
    outlinePoints.push(`${x},${MARGIN_T + CHART_H - h}`);
  });

  return (
    <div style={{ overflowX: "auto" }}>
      <svg
        viewBox={`0 0 ${W} ${SVG_H}`}
        className="w-full"
        style={{ maxWidth: W, minWidth: 400, display: "block" }}
        aria-label={t("permutation.results.nullDistribution")}
      >
        {/* Left Y-axis — iteration counts (blue) */}
        {nullTicks.map((tick) => {
          const y = MARGIN_T + CHART_H - Math.round((tick / maxNullCount) * CHART_H);
          return (
            <g key={`lyt-${tick}`}>
              <line x1={MARGIN_L - 3} y1={y} x2={MARGIN_L} y2={y} stroke="#3b82f6" strokeWidth={0.5} />
              <text x={MARGIN_L - 5} y={y + 3} textAnchor="end" fontSize={7} fontFamily="monospace" fill="#3b82f6">{tick}</text>
            </g>
          );
        })}
        <text x={4} y={MARGIN_T - 3} fontSize={8} fill="#3b82f6" fontFamily="sans-serif" fontWeight="600">N iter.</text>

        {/* Right Y-axis — observed event counts (orange) */}
        {obsTicks.map((tick) => {
          const y = MARGIN_T + CHART_H - Math.round((tick / maxObsCount) * CHART_H);
          return (
            <g key={`ryt-${tick}`}>
              <line x1={MARGIN_L + CHART_W} y1={y} x2={MARGIN_L + CHART_W + 3} y2={y} stroke="#f97316" strokeWidth={0.5} />
              <text x={MARGIN_L + CHART_W + 5} y={y + 3} textAnchor="start" fontSize={7} fontFamily="monospace" fill="#f97316">{tick}</text>
            </g>
          );
        })}
        <text x={W - 2} y={MARGIN_T - 3} textAnchor="end" fontSize={8} fill="#f97316" fontFamily="sans-serif" fontWeight="600">N events</text>

        {/* Null distribution bars (blue) */}
        {nullBins.map((bin, i) => {
          const nullH = Math.round((nullCounts[i] / maxNullCount) * CHART_H);
          const x = MARGIN_L + i * (barW + 1);
          return (
            <g key={i}>
              <title>{`ΔΨ ≈ ${bin.toFixed(2)} — H₀: ${nullCounts[i]}`}</title>
              <rect
                x={x} y={MARGIN_T + CHART_H - nullH}
                width={barW} height={nullH}
                fill="#3b82f6" opacity={0.45}
              />
              {i % 5 === 0 && (
                <text
                  x={x + barW / 2} y={MARGIN_T + CHART_H + 14}
                  textAnchor="middle" fontSize={8}
                  fontFamily="monospace" fill="#94a3b8"
                >
                  {bin.toFixed(1)}
                </text>
              )}
            </g>
          );
        })}
        {/* Observed ΔΨ — proportionate dashed lines (orange) */}
        {obsBins.map((bin, i) => {
          const c = obsCounts[i] ?? 0;
          if (c <= 0) return null;
          const x = MARGIN_L + i * (barW + 1) + barW / 2;
          const h = Math.round((c / maxObsCount) * CHART_H);
          return (
            <g key={`obs-${i}`}>
              <title>{`ΔΨ ≈ ${bin.toFixed(2)} — observed: ${c}`}</title>
              <line
                x1={x} y1={MARGIN_T + CHART_H}
                x2={x} y2={MARGIN_T + CHART_H - h}
                stroke="#f97316" strokeWidth={1.5}
                strokeDasharray="4 3" opacity={0.85}
              />
            </g>
          );
        })}
        {/* Outline connecting tops of orange dashed lines */}
        {outlinePoints.length > 1 && (
          <polyline
            points={outlinePoints.join(" ")}
            fill="none" stroke="#f97316" strokeWidth={1.5} opacity={0.9}
          />
        )}
        <line x1={MARGIN_L} y1={MARGIN_T + CHART_H} x2={MARGIN_L + CHART_W} y2={MARGIN_T + CHART_H} stroke="var(--svg-panel-border)" strokeWidth={0.5} />
        <text x={MARGIN_L + CHART_W / 2} y={SVG_H - 2} textAnchor="middle" fontSize={8} fill="hsl(var(--muted-foreground))" fontFamily="sans-serif" fontStyle="italic" fontWeight="600">ΔΨ</text>
      </svg>
      <div className="flex items-center gap-4 text-[11px] text-muted-foreground mt-1.5">
        <span className="flex items-center gap-1">
          <span className="inline-block w-4 h-2.5 rounded-sm bg-blue-500/45" />
          {t("permutation.results.nullDistribution")} (permutations)
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-4 h-0.5 border-t-2 border-dashed border-orange-500" />
          ΔΨ {t("permutation.results.observedDeltaPsi").toLowerCase()}
        </span>
      </div>
    </div>
  );
}

/** Generate nice round tick values for a Y-axis. */
function _niceTicks(maxVal: number, count: number): number[] {
  if (maxVal <= 0) return [0];
  const rough = maxVal / count;
  const mag = Math.pow(10, Math.floor(Math.log10(rough)));
  const residual = rough / mag;
  const nice = residual <= 1.5 ? 1 : residual <= 3.5 ? 2 : residual <= 7.5 ? 5 : 10;
  const step = nice * mag;
  const ticks: number[] = [];
  for (let v = step; v <= maxVal * 1.01; v += step) {
    ticks.push(Math.round(v));
  }
  return ticks.length ? ticks : [Math.round(maxVal)];
}

// ---------------------------------------------------------------------------
// Top-events table
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
                <td className="px-2 py-1 border border-border text-muted-foreground whitespace-nowrap">
                  {ev.n1} / {ev.n2}
                  {ev.exact && (
                    <span
                      className="ml-1 px-1 py-px rounded bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300 text-[8px] font-semibold"
                      title={ev.n_splits != null ? t("permutation.results.exactSplits", { n: ev.n_splits }) : undefined}
                    >
                      {t("permutation.results.exactBadge")}
                    </span>
                  )}
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
// Aggregate metric results table (D11)
// ---------------------------------------------------------------------------

function MetricResultsTable({ metrics }: { metrics: MetricPermResult[] }) {
  const t = useT();
  if (!metrics.length) return null;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[10px] border-collapse">
        <thead>
          <tr className="bg-muted/50">
            <th className="text-left px-2 py-1.5 font-semibold text-muted-foreground border border-border">{t("permutation.results.metric")}</th>
            <th className="text-right px-2 py-1.5 font-semibold text-muted-foreground border border-border">{t("permutation.results.observedDelta")}</th>
            <th className="text-right px-2 py-1.5 font-semibold text-muted-foreground border border-border">{t("permutation.results.empiricalP")}</th>
            <th className="text-right px-2 py-1.5 font-semibold text-muted-foreground border border-border">{t("permutation.results.validEvents")}</th>
            <th className="text-left px-2 py-1.5 font-semibold text-muted-foreground border border-border">{t("permutation.results.nGroups")}</th>
          </tr>
        </thead>
        <tbody>
          {metrics.map((m) => {
            const p = m.empirical_p_value;
            const sig01 = p !== null && p < 0.01;
            const sig05 = p !== null && p < 0.05;
            return (
              <tr key={m.metric_name} className="hover:bg-muted/30 transition-colors">
                <td className="px-2 py-1 border border-border font-semibold text-foreground" title={m.metric_name}>
                  {m.label || m.metric_name}
                </td>
                <td className="px-2 py-1 border border-border text-right tabular-nums">
                  {m.observed_stat !== null
                    ? (m.observed_stat >= 0 ? "+" : "") + m.observed_stat.toFixed(3)
                    : "—"}
                </td>
                <td className={`px-2 py-1 border border-border text-right tabular-nums font-semibold ${
                  sig01 ? "text-green-600 dark:text-green-400" :
                  sig05 ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground"
                }`}>
                  {fmtP(p)}
                </td>
                <td className="px-2 py-1 border border-border text-right tabular-nums text-muted-foreground">
                  {m.n_valid}
                </td>
                <td className="px-2 py-1 border border-border text-muted-foreground">
                  {m.n_g1} / {m.n_g2}
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
// Main component
// ---------------------------------------------------------------------------

interface PermutationPanelProps {
  analysisId: string;
  fdrThreshold?: number;
  deltaPsiMin?: number;
  /** Optional p-value maximum of the deep analysis (A8). */
  pvalueThreshold?: number | null;
}

export function PermutationPanel({ analysisId, fdrThreshold, deltaPsiMin, pvalueThreshold }: PermutationPanelProps) {
  const t = useT();
  const [nIterations, setNIterations] = useState(500);
  const [result, setResult] = useState<PermutationResponse | null>(null);

  const { mutate, isPending, isError } = useMutation({
    mutationFn: () => runPermutationTest(analysisId, nIterations, fdrThreshold, deltaPsiMin, pvalueThreshold),
    onSuccess: (data) => setResult(data),
  });

  // Resolution warning (C3): with few replicates only C(n1+n2, n1) distinct
  // label splits exist, so the smallest attainable p-value may exceed 0.05.
  const nRep1 = result?.n_replicates_g1 ?? null;
  const nRep2 = result?.n_replicates_g2 ?? null;
  const minP = result?.min_p_attainable ?? null;
  const nSplits = nRep1 !== null && nRep2 !== null ? binom(nRep1 + nRep2, nRep1) : null;
  const lowResolution = minP !== null && minP > 0.05;

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
          {/* Summary badges */}
          <div className="flex flex-wrap gap-3">
            <div className="text-center px-3 py-2 rounded-lg bg-muted/40 border border-border">
              <p className="text-[9px] text-muted-foreground uppercase tracking-wide">{t("permutation.results.eventsTested")}</p>
              <p className="text-base font-bold tabular-nums">{result.n_events_tested}</p>
            </div>
            {result.n_total_events > 0 && result.n_total_events !== result.n_events_tested && (
              <div className="text-center px-3 py-2 rounded-lg bg-muted/40 border border-border">
                <p className="text-[9px] text-muted-foreground uppercase tracking-wide">{t("permutation.results.totalEvents")}</p>
                <p className="text-base font-bold tabular-nums text-muted-foreground">{result.n_total_events}</p>
              </div>
            )}
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
            {nRep1 !== null && nRep2 !== null && (
              <div className="text-center px-3 py-2 rounded-lg bg-muted/40 border border-border">
                <p className="text-[9px] text-muted-foreground uppercase tracking-wide">{t("permutation.results.replicates")}</p>
                <p className="text-base font-bold tabular-nums">{nRep1} / {nRep2}</p>
              </div>
            )}
            {result.exact_fraction != null && (
              <div
                className="text-center px-3 py-2 rounded-lg bg-indigo-50 border border-indigo-200 dark:bg-indigo-950/20 dark:border-indigo-700"
                title={t("permutation.results.exactFractionHint", { pct: Math.round(result.exact_fraction * 100) })}
              >
                <p className="text-[9px] text-muted-foreground uppercase tracking-wide">{t("permutation.results.exactFraction")}</p>
                <p className="text-base font-bold tabular-nums text-indigo-700 dark:text-indigo-300">
                  {Math.round(result.exact_fraction * 100)}%
                </p>
              </div>
            )}
            {minP !== null && (
              <div className={`text-center px-3 py-2 rounded-lg border ${
                lowResolution
                  ? "bg-amber-50 border-amber-200 dark:bg-amber-950/20 dark:border-amber-700"
                  : "bg-muted/40 border-border"
              }`}>
                <p className="text-[9px] text-muted-foreground uppercase tracking-wide">{t("permutation.results.minPAttainable")}</p>
                <p className={`text-base font-bold tabular-nums ${lowResolution ? "text-amber-700 dark:text-amber-400" : ""}`}>
                  {fmtP(minP)}
                </p>
              </div>
            )}
          </div>

          {/* Low-resolution warning (few replicates) */}
          {lowResolution && nRep1 !== null && nRep2 !== null && (
            <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-700 text-[10px] text-amber-800 dark:text-amber-300 leading-relaxed">
              <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
              </svg>
              <span>
                {t("permutation.results.lowResolution", {
                  n1: nRep1,
                  n2: nRep2,
                  n: nSplits ?? "?",
                  p: fmtP(minP),
                })}
              </span>
            </div>
          )}

          {/* Null distribution */}
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
            <p className="text-[9px] text-muted-foreground italic mt-1 leading-relaxed">
              {t("permutation.results.method")}
            </p>
          </div>

          <div
            className="p-3 rounded-lg bg-muted/30 border border-border text-[9px] leading-relaxed text-muted-foreground"
            dangerouslySetInnerHTML={{ __html: t("permutation.results.interpretation") }}
          />

          {/* Top events */}
          <div>
            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-2">
              {t("permutation.results.topEvents")}
            </p>
            <TopEventsTable events={result.events} />
          </div>

          {/* Aggregate metric tests (D11) */}
          {result.metric_results && result.metric_results.length > 0 && (
            <div>
              <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                {t("permutation.results.metricTitle")}
              </p>
              <MetricResultsTable metrics={result.metric_results} />
              <div
                className="mt-2 p-3 rounded-lg bg-muted/30 border border-border text-[9px] leading-relaxed text-muted-foreground"
                dangerouslySetInnerHTML={{ __html: t("permutation.results.interpretationMetric") }}
              />
            </div>
          )}
        </div>
      )}

      {/* Empty state */}
      {!result && !isPending && (
        <div className="py-8 text-center text-muted-foreground">
          <p className="text-sm">{t("permutation.empty.main")}</p>
          <p className="text-[10px] mt-1">{t("permutation.empty.params")}</p>
        </div>
      )}

      <ScienceNote
        title={t("scienceNotes.permutation.title")}
        body={t("scienceNotes.permutation.body")}
        refs={["permutation_phipson", "benjamini_hochberg", "rmats"]}
      />
    </div>
  );
}
