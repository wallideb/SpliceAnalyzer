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
import type { PermutationResponse } from "@/types/splice";

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

  const W = 500;
  const MARGIN_T = 18;
  const CHART_H = 110;
  const MARGIN_B = 24;
  const SVG_H = MARGIN_T + CHART_H + MARGIN_B;

  const maxNullCount = Math.max(...nullCounts, 1);
  const n = nullBins.length;
  const barW = Math.max(3, Math.floor(W / n) - 1);

  return (
    <div style={{ overflowX: "auto" }}>
      <svg
        viewBox={`0 0 ${W} ${SVG_H}`}
        className="w-full"
        style={{ maxWidth: W, minWidth: 360, display: "block" }}
        aria-label={t("permutation.results.nullDistribution")}
      >
        {/* Null distribution bars (blue) */}
        {nullBins.map((bin, i) => {
          const nullH = Math.round((nullCounts[i] / maxNullCount) * CHART_H);
          const x = i * (barW + 1);
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
        {/* Observed ΔΨ as vertical dashed lines (orange) */}
        {obsBins.map((bin, i) => {
          if ((obsCounts[i] ?? 0) <= 0) return null;
          const x = i * (barW + 1) + barW / 2;
          return (
            <g key={`obs-${i}`}>
              <title>{`ΔΨ ≈ ${bin.toFixed(2)} — observed: ${obsCounts[i]}`}</title>
              <line
                x1={x} y1={MARGIN_T}
                x2={x} y2={MARGIN_T + CHART_H}
                stroke="#f97316" strokeWidth={1.5}
                strokeDasharray="4 3" opacity={0.85}
              />
              <text
                x={x} y={MARGIN_T - 2}
                textAnchor="middle" fontSize={7}
                fontFamily="monospace" fill="#f97316" fontWeight="600"
              >
                {obsCounts[i]}
              </text>
            </g>
          );
        })}
        <line x1={0} y1={MARGIN_T + CHART_H} x2={W} y2={MARGIN_T + CHART_H} stroke="var(--svg-panel-border)" strokeWidth={0.5} />
        <text x={2} y={MARGIN_T - 3} fontSize={8} fill="hsl(var(--muted-foreground))" fontFamily="sans-serif" fontWeight="600">N</text>
        <text x={W} y={SVG_H - 2} textAnchor="end" fontSize={8} fill="hsl(var(--muted-foreground))" fontFamily="sans-serif" fontStyle="italic" fontWeight="600">ΔΨ</text>
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
// Main component
// ---------------------------------------------------------------------------

export function PermutationPanel({ analysisId }: { analysisId: string }) {
  const t = useT();
  const [nIterations, setNIterations] = useState(500);
  const [result, setResult] = useState<PermutationResponse | null>(null);

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
          {/* Summary badges */}
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
