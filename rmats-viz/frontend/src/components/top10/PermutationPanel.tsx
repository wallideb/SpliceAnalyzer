"use client";

/**
 * PermutationPanel
 * =================
 * Visualisation du test de permutation patients/contrôles.
 *
 * Fonctionnalités :
 *  • Paramètres configurables : N itérations (50 – 2000)
 *  • Bouton "Lancer le test" → POST /api/v1/splice/permutation/{analysisId}
 *  • Distribution nulle globale (histogramme SVG bleu)
 *  • Histogramme des ΔΨ observés (superposé en orange)
 *  • % événements significatifs à p < 0.05 et p < 0.01
 *  • Tableau des top 10 événements les plus significatifs
 *  • Progress bar + spinner pendant calcul
 */

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { runPermutationTest } from "@/lib/api/splice";
import type { PermutationResponse } from "@/types/splice";

// ---------------------------------------------------------------------------
// Dual-histogram SVG
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
  const H = 110;
  const MARGIN_T = 16;
  const MARGIN_B = 24;
  const CHART_H = H;
  const SVG_H = MARGIN_T + CHART_H + MARGIN_B;

  const maxCount = Math.max(...nullCounts, ...obsCounts, 1);
  const n = nullBins.length;
  const barW = Math.max(3, Math.floor(W / n) - 1);

  return (
    <div style={{ overflowX: "auto" }}>
      <svg
        viewBox={`0 0 ${W} ${SVG_H}`}
        style={{ width: W, height: SVG_H, display: "block" }}
        aria-label="Distribution des ΔΨ sous H0 (permutation)"
      >
        {nullBins.map((bin, i) => {
          const nullH  = Math.round((nullCounts[i]  / maxCount) * CHART_H);
          const obsH   = Math.round(((obsCounts[i] ?? 0) / maxCount) * CHART_H);
          const x = i * (barW + 1);
          return (
            <g key={i}>
              <title>{`ΔΨ ≈ ${bin.toFixed(2)} — H₀: ${nullCounts[i]}, observé: ${obsCounts[i] ?? 0}`}</title>
              {/* Null (blue) */}
              <rect
                x={x}
                y={MARGIN_T + CHART_H - nullH}
                width={barW}
                height={nullH}
                fill="#3b82f6"
                opacity={0.45}
              />
              {/* Observed (orange) — on top */}
              {(obsCounts[i] ?? 0) > 0 && (
                <rect
                  x={x}
                  y={MARGIN_T + CHART_H - obsH}
                  width={barW}
                  height={obsH}
                  fill="#f97316"
                  opacity={0.7}
                />
              )}
              {/* X-axis label every 5 bins */}
              {i % 5 === 0 && (
                <text
                  x={x + barW / 2}
                  y={MARGIN_T + CHART_H + 12}
                  textAnchor="middle"
                  fontSize={6.5}
                  fontFamily="monospace"
                  fill="#94a3b8"
                >
                  {bin.toFixed(1)}
                </text>
              )}
            </g>
          );
        })}
        {/* X-axis */}
        <line
          x1={0} y1={MARGIN_T + CHART_H}
          x2={W} y2={MARGIN_T + CHART_H}
          stroke="#334155" strokeWidth={0.5}
        />
        {/* Y-axis label */}
        <text x={2} y={MARGIN_T - 3} fontSize={6.5} fill="#64748b" fontFamily="sans-serif">
          N
        </text>
        {/* X-axis title */}
        <text x={W} y={SVG_H - 2} textAnchor="end" fontSize={6.5} fill="#64748b" fontFamily="sans-serif" fontStyle="italic">
          ΔΨ
        </text>
      </svg>
      {/* Legend */}
      <div className="flex items-center gap-4 text-[9px] text-muted-foreground mt-1">
        <span className="flex items-center gap-1">
          <span className="inline-block w-4 h-2.5 rounded-sm bg-blue-500/45" />
          Distribution nulle H₀ (permutations)
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-4 h-2.5 rounded-sm bg-orange-500/70" />
          ΔΨ observés
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Top-events table
// ---------------------------------------------------------------------------

function TopEventsTable({ result }: { result: PermutationResponse }) {
  const sorted = [...result.events]
    .filter((e) => e.empirical_p_value !== null)
    .sort((a, b) => (a.empirical_p_value ?? 1) - (b.empirical_p_value ?? 1))
    .slice(0, 15);

  if (!sorted.length) return null;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[10px] border-collapse">
        <thead>
          <tr className="bg-muted/50">
            <th className="text-left px-2 py-1.5 font-semibold text-muted-foreground border border-border">Gène</th>
            <th className="text-right px-2 py-1.5 font-semibold text-muted-foreground border border-border">ΔΨ observé</th>
            <th className="text-right px-2 py-1.5 font-semibold text-muted-foreground border border-border">p empirique</th>
            <th className="text-left px-2 py-1.5 font-semibold text-muted-foreground border border-border">N groupes</th>
            <th className="text-left px-2 py-1.5 font-semibold text-muted-foreground border border-border">Significatif</th>
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
            Nombre d&apos;itérations
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
            Plus d&apos;itérations = distribution nulle plus précise, mais calcul plus long.
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
          {isPending ? `Calcul en cours (${nIterations} itér.)…` : "Lancer le test de permutation"}
        </button>
      </div>

      {isError && (
        <p className="text-xs text-red-500">
          Erreur lors du calcul. Vérifiez que les données PSI sont disponibles.
        </p>
      )}

      {/* ── Results ── */}
      {result && (
        <div className="space-y-5">

          {/* Summary badges */}
          <div className="flex flex-wrap gap-3">
            <div className="text-center px-3 py-2 rounded-lg bg-muted/40 border border-border">
              <p className="text-[9px] text-muted-foreground uppercase tracking-wide">Événements testés</p>
              <p className="text-base font-bold tabular-nums">{result.n_events_tested}</p>
            </div>
            <div className="text-center px-3 py-2 rounded-lg bg-muted/40 border border-border">
              <p className="text-[9px] text-muted-foreground uppercase tracking-wide">Itérations</p>
              <p className="text-base font-bold tabular-nums">{result.n_iterations}</p>
            </div>
            {result.pct_p05 !== null && (
              <div className="text-center px-3 py-2 rounded-lg bg-amber-50 border border-amber-200 dark:bg-amber-950/20 dark:border-amber-700">
                <p className="text-[9px] text-muted-foreground uppercase tracking-wide">Sig. p&lt;0.05</p>
                <p className="text-base font-bold tabular-nums text-amber-700 dark:text-amber-400">
                  {result.pct_p05}%
                </p>
              </div>
            )}
            {result.pct_p01 !== null && (
              <div className="text-center px-3 py-2 rounded-lg bg-green-50 border border-green-200 dark:bg-green-950/20 dark:border-green-700">
                <p className="text-[9px] text-muted-foreground uppercase tracking-wide">Sig. p&lt;0.01</p>
                <p className="text-base font-bold tabular-nums text-green-700 dark:text-green-400">
                  {result.pct_p01}%
                </p>
              </div>
            )}
          </div>

          {/* Distribution histogram */}
          <div>
            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-2">
              Distribution des ΔΨ sous H₀ vs observés
            </p>
            <DualHistogram
              nullBins={result.global_null_hist_bins}
              nullCounts={result.global_null_hist_counts}
              obsBins={result.observed_hist_bins}
              obsCounts={result.observed_hist_counts}
            />
          </div>

          {/* Interpretation */}
          <div className="p-3 rounded-lg bg-muted/30 border border-border text-[9px] leading-relaxed text-muted-foreground">
            <strong className="text-foreground">Interprétation :</strong>{" "}
            La distribution bleue représente la distribution nulle des ΔΨ sous l&apos;hypothèse
            H₀ (absence de splicing différentiel, labels patients/contrôles aléatoires).
            La distribution orange représente les ΔΨ réellement observés dans les données.
            Un déplacement de la distribution orange vers des valeurs extrêmes (±1) indique
            un signal biologique réel.
            La p-value empirique est calculée individuellement pour chaque événement SE.
          </div>

          {/* Top events table */}
          <div>
            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-2">
              Top événements les plus significatifs (test de permutation)
            </p>
            <TopEventsTable result={result} />
          </div>
        </div>
      )}

      {/* Empty state */}
      {!result && !isPending && (
        <div className="py-8 text-center text-muted-foreground">
          <p className="text-sm">
            Lancez le test de permutation pour estimer la significativité empirique
            des ΔΨ observés.
          </p>
          <p className="text-[10px] mt-1">
            Le test randomise les labels patients/contrôles et reconstruit
            la distribution nulle des différences d&apos;inclusion.
          </p>
        </div>
      )}
    </div>
  );
}
