"use client";

/**
 * MotifPatternPanel
 * ==================
 * Aggregate splice-signal analysis panel — displayed in the main content area
 * when the user selects the "Motifs récurrents" sidebar tab in the deep-analysis
 * view (mode === "motifs").
 *
 * Shows:
 *  - Summary: n SE events analysed, n canonical clusters
 *  - Exon size histogram (SVG bar chart, bins of 25 nt)
 *  - 5'SS donor sequence logo (9 nt around GT)
 *  - 3'SS acceptor sequence logo (23 nt around AG)
 *  - PPT score distribution (score bar list)
 *  - Frame breakdown bar (in_frame / frameshift / non_coding / unknown)
 *  - Branch-point detection rate
 *
 * Data is fetched from GET /api/v1/splice/patterns/{analysisId}.
 * A "Calculer" button triggers POST /api/v1/splice/compute/{analysisId}.
 */

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getSplicePatterns, computeSpliceFeatures } from "@/lib/api/splice";
import type { SplicingEvent } from "@/types/event";
import type { ExonSizeStats } from "@/types/splice";
import { ConsensusLogoPanel } from "./ConsensusLogoPanel";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface MotifPatternPanelProps {
  events: SplicingEvent[];
  analysisId: string;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Thin horizontal progress bar. */
function Bar({ pct, className = "" }: { pct: number; className?: string }) {
  return (
    <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
      <div
        className={`h-full rounded-full ${className}`}
        style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
      />
    </div>
  );
}

/** SVG exon-size histogram — mean & median lines, tooltips, axis labels. */
function ExonSizeHistogram({ stats }: { stats: ExonSizeStats }) {
  const { distribution, mean, median } = stats;
  const [hoveredBin, setHoveredBin] = useState<{ bin: number; count: number; x: number; y: number } | null>(null);

  if (!distribution.length) return null;

  const W = 340;
  const H = 100;
  // bottom margin for x-axis labels + title, top margin for stat line labels
  const MARGIN_TOP = 14;
  const MARGIN_BOTTOM = 22;
  const CHART_H = H; // chart area height (bars)
  const SVG_H = MARGIN_TOP + CHART_H + MARGIN_BOTTOM;

  const sorted = [...distribution].sort((a, b) => a.bin - b.bin);
  const maxCount = Math.max(...sorted.map((d) => d.count), 1);
  const barW = Math.max(4, Math.floor(W / sorted.length) - 1);

  // Convert a nucleotide value to an X coordinate within the chart
  const valueToX = (val: number): number => {
    const idx = sorted.findIndex((d) => d.bin >= val);
    const i = Math.max(0, idx === -1 ? sorted.length - 1 : idx);
    return i * (barW + 1) + barW / 2;
  };

  const meanX = mean !== null ? valueToX(mean) : null;
  const medianX = median !== null ? valueToX(median) : null;

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${W} ${SVG_H}`}
        className="w-full max-w-[340px]"
        aria-label="Distribution des tailles d'exons sautés"
        style={{ overflow: "visible" }}
      >
        {/* Bars */}
        {sorted.map((d, i) => {
          const barH = Math.max(1, Math.round((d.count / maxCount) * CHART_H));
          const x = i * (barW + 1);
          const y = MARGIN_TOP + CHART_H - barH;
          return (
            <g key={d.bin}>
              <rect
                x={x}
                y={y}
                width={barW}
                height={barH}
                className="fill-blue-500/70 hover:fill-blue-500 cursor-pointer transition-colors"
                rx={2}
                title={`${d.bin}–${d.bin + 25} nt : ${d.count} événements`}
                onMouseEnter={() =>
                  setHoveredBin({ bin: d.bin, count: d.count, x: x + barW / 2, y })
                }
                onMouseLeave={() => setHoveredBin(null)}
              />
              {/* x-axis label every 4 bins */}
              {i % 4 === 0 && (
                <text
                  x={x + barW / 2}
                  y={MARGIN_TOP + CHART_H + 10}
                  textAnchor="middle"
                  fontSize={6.5}
                  className="fill-muted-foreground"
                >
                  {d.bin}
                </text>
              )}
            </g>
          );
        })}

        {/* Baseline (x-axis) */}
        <line
          x1={0}
          y1={MARGIN_TOP + CHART_H}
          x2={W}
          y2={MARGIN_TOP + CHART_H}
          strokeWidth={0.5}
          className="stroke-border"
        />

        {/* X-axis title */}
        <text
          x={W}
          y={SVG_H - 2}
          textAnchor="end"
          fontSize={6.5}
          className="fill-muted-foreground"
          fontStyle="italic"
        >
          Taille (nt)
        </text>

        {/* Mean line (red dashed) */}
        {meanX !== null && mean !== null && (
          <g>
            <line
              x1={meanX}
              y1={MARGIN_TOP}
              x2={meanX}
              y2={MARGIN_TOP + CHART_H}
              stroke="#ef4444"
              strokeWidth={1}
              strokeDasharray="3 2"
            />
            <text
              x={meanX + 2}
              y={MARGIN_TOP - 2}
              fontSize={6}
              fill="#ef4444"
              textAnchor="start"
            >
              Moy. {Math.round(mean)} nt
            </text>
          </g>
        )}

        {/* Median line (orange dashed) */}
        {medianX !== null && median !== null && (
          <g>
            <line
              x1={medianX}
              y1={MARGIN_TOP}
              x2={medianX}
              y2={MARGIN_TOP + CHART_H}
              stroke="#f97316"
              strokeWidth={1}
              strokeDasharray="3 2"
            />
            <text
              x={medianX + 2}
              y={MARGIN_TOP + 8}
              fontSize={6}
              fill="#f97316"
              textAnchor="start"
            >
              Méd. {Math.round(median)} nt
            </text>
          </g>
        )}

        {/* Tooltip (SVG foreignObject) */}
        {hoveredBin && (
          <foreignObject
            x={Math.min(hoveredBin.x + 4, W - 90)}
            y={Math.max(hoveredBin.y - 20, MARGIN_TOP)}
            width={90}
            height={24}
          >
            <div
              className="bg-popover text-popover-foreground border border-border rounded px-1.5 py-0.5 text-[9px] shadow-sm whitespace-nowrap"
              style={{ pointerEvents: "none" }}
            >
              {hoveredBin.bin}–{hoveredBin.bin + 25} nt : <strong>{hoveredBin.count}</strong> évén.
            </div>
          </foreignObject>
        )}
      </svg>

      {/* Legend below the chart */}
      <div className="flex items-center gap-4 mt-1 text-[9px] text-muted-foreground select-none">
        <span className="flex items-center gap-1">
          <svg width="18" height="8" className="inline-block">
            <line x1="0" y1="4" x2="18" y2="4" stroke="#ef4444" strokeWidth="1.5" strokeDasharray="3 2" />
          </svg>
          Moyenne
        </span>
        <span className="flex items-center gap-1">
          <svg width="18" height="8" className="inline-block">
            <line x1="0" y1="4" x2="18" y2="4" stroke="#f97316" strokeWidth="1.5" strokeDasharray="3 2" />
          </svg>
          Médiane
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function MotifPatternPanel({ events, analysisId }: MotifPatternPanelProps) {
  const qc = useQueryClient();

  const seCount = events.filter((e) => e.event_type === "SE").length;

  const { data, isLoading, isError } = useQuery({
    queryKey: ["splice-patterns", analysisId],
    queryFn: () => getSplicePatterns(analysisId),
    enabled: !!analysisId,
    staleTime: 10 * 60 * 1000,
    retry: false,
  });

  const compute = useMutation({
    mutationFn: () => computeSpliceFeatures(analysisId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["splice-patterns", analysisId] }),
  });

  // ── Loading ──────────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="space-y-3 p-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-6 rounded bg-muted animate-pulse" />
        ))}
      </div>
    );
  }

  // ── Not computed / error ─────────────────────────────────────────────────
  if (isError || !data) {
    return (
      <div className="flex flex-col items-center gap-4 py-10 text-center">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="w-10 h-10 text-muted-foreground/40"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1.5}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
        </svg>
        <div>
          <p className="text-sm font-semibold text-foreground mb-1">
            Analyse de patterns non calculée
          </p>
          <p className="text-xs text-muted-foreground max-w-xs leading-relaxed">
            Calculez les features d&apos;épissage pour les {seCount} événements SE de cette analyse
            afin de visualiser les patterns récurrents (sites GT-AG, PPT, point de branchement,
            classe de cadre de lecture).
          </p>
        </div>
        <button
          onClick={() => compute.mutate()}
          disabled={compute.isPending}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-semibold bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50 transition-colors"
        >
          {compute.isPending && (
            <svg className="animate-spin w-4 h-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          )}
          {compute.isPending ? "Calcul en cours…" : "Calculer les features"}
        </button>
        {compute.isError && (
          <p className="text-xs text-red-500">Erreur lors du calcul. Réessayez.</p>
        )}
      </div>
    );
  }

  // ── Computed ─────────────────────────────────────────────────────────────
  const { exon_sizes, donor_sites, acceptor_sites, ppt, frame, bp_found_pct } = data;

  // Frame totals for bar widths
  const frameTotal = (frame.in_frame + frame.frameshift + frame.non_coding + frame.unknown) || 1;
  const frameBars = [
    { label: "In-frame",   value: frame.in_frame,   pct: (frame.in_frame / frameTotal) * 100,   color: "bg-green-500" },
    { label: "Frameshift", value: frame.frameshift,  pct: (frame.frameshift / frameTotal) * 100,  color: "bg-red-500" },
    { label: "Non-codant", value: frame.non_coding,  pct: (frame.non_coding / frameTotal) * 100,  color: "bg-slate-400" },
    { label: "Inconnu",    value: frame.unknown,     pct: (frame.unknown / frameTotal) * 100,     color: "bg-muted-foreground/30" },
  ];

  return (
    <div className="space-y-6 text-xs">

      {/* ── Summary header ── */}
      <div className="flex flex-wrap gap-4">
        <SummaryChip label="Événements SE" value={data.n_se_events} />
        <SummaryChip label="Analysés (seq.)" value={data.n_analyzed} />
        <SummaryChip label="Clusters" value={data.clusters.n_clusters} />
        {!data.fasta_available && (
          <span className="self-center text-[10px] text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded px-2 py-1">
            FASTA non disponible — tailles depuis coords uniquement
          </span>
        )}
      </div>

      {/* ── Exon size distribution ── */}
      {exon_sizes && (
        <Section title="Distribution des tailles d'exons sautés (nt)">
          {exon_sizes.mean !== null && (
            <div className="flex gap-4 mb-2 text-[10px] text-muted-foreground">
              <span>Moy. <strong className="text-foreground">{exon_sizes.mean} nt</strong></span>
              <span>Méd. <strong className="text-foreground">{exon_sizes.median} nt</strong></span>
              <span>Min <strong className="text-foreground">{exon_sizes.min}</strong></span>
              <span>Max <strong className="text-foreground">{exon_sizes.max}</strong></span>
            </div>
          )}
          <ExonSizeHistogram stats={exon_sizes} />
        </Section>
      )}

      {/* ── 5'SS donor logo ── */}
      {donor_sites && donor_sites.pwm.length > 0 && (
        <Section title={`Site donneur 5'SS — ${donor_sites.n_sequences} séquences · ${donor_sites.pct_canonical}% GT canonique`}>
          {donor_sites.consensus && (
            <p className="text-[10px] text-muted-foreground mb-1">
              Consensus IUPAC : <code className="font-mono font-bold text-foreground">{donor_sites.consensus}</code>
            </p>
          )}
          <ConsensusLogoPanel
            pwm={donor_sites.pwm}
            title="Logo 5'SS (9 nt)"
            startPosition={-3}
            skipZero
            canonicalPositions={[1, 2]}
            id="logo-donor"
          />
        </Section>
      )}

      {/* ── 3'SS acceptor logo ── */}
      {acceptor_sites && acceptor_sites.pwm.length > 0 && (
        <Section title={`Site accepteur 3'SS — ${acceptor_sites.n_sequences} séquences · ${acceptor_sites.pct_canonical}% AG canonique`}>
          {acceptor_sites.consensus && (
            <p className="text-[10px] text-muted-foreground mb-1">
              Consensus IUPAC : <code className="font-mono font-bold text-foreground">{acceptor_sites.consensus}</code>
            </p>
          )}
          <ConsensusLogoPanel
            pwm={acceptor_sites.pwm}
            title="Logo 3'SS (23 nt)"
            startPosition={-20}
            skipZero
            canonicalPositions={[-2, -1]}
            id="logo-acceptor"
          />
        </Section>
      )}

      {/* ── PPT score distribution ── */}
      {ppt && ppt.scores.length > 0 && (
        <Section title={`Zone PPT — score moyen ${ppt.mean_score !== null ? Math.round(ppt.mean_score * 100) + "%" : "—"} · run Y le plus long : ${ppt.mean_longest_run ?? "—"} nt`}>
          <div className="flex flex-wrap gap-1 max-h-24 overflow-y-auto">
            {ppt.scores.slice(0, 50).map((s, i) => (
              <div key={i} className="flex items-center gap-1 w-14">
                <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full rounded-full bg-amber-400"
                    style={{ width: `${Math.round(s * 100)}%` }}
                  />
                </div>
                <span className="text-[9px] tabular-nums text-muted-foreground w-5 text-right">
                  {Math.round(s * 100)}
                </span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* ── Frame breakdown ── */}
      <Section title="Classe de cadre de lecture (exon sauté)">
        {/* Prominent summary badges */}
        <div className="flex flex-wrap gap-2 mb-3">
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border bg-green-50 border-green-200 dark:bg-green-900/20 dark:border-green-700">
            <span className="text-green-700 dark:text-green-300 text-base font-bold tabular-nums">{frame.in_frame}</span>
            <span className="text-[10px] font-semibold text-green-700 dark:text-green-400 uppercase tracking-wide">in-frame</span>
          </span>
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border bg-red-50 border-red-200 dark:bg-red-900/20 dark:border-red-700">
            <span className="text-red-700 dark:text-red-300 text-base font-bold tabular-nums">{frame.frameshift}</span>
            <span className="text-[10px] font-semibold text-red-700 dark:text-red-400 uppercase tracking-wide">frameshift</span>
          </span>
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border bg-slate-50 border-slate-200 dark:bg-slate-700/30 dark:border-slate-600">
            <span className="text-slate-600 dark:text-slate-300 text-base font-bold tabular-nums">{frame.non_coding}</span>
            <span className="text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">non-codant</span>
          </span>
          {frame.unknown > 0 && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border bg-muted border-border">
              <span className="text-muted-foreground text-base font-bold tabular-nums">{frame.unknown}</span>
              <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">inconnu</span>
            </span>
          )}
        </div>
        {/* Proportional bars */}
        <div className="space-y-1.5">
          {frameBars.filter(fb => fb.value > 0).map((fb) => (
            <div key={fb.label} className="flex items-center gap-2">
              <span className="w-20 text-[10px] text-muted-foreground truncate">{fb.label}</span>
              <Bar pct={fb.pct} className={fb.color} />
              <span className="w-10 text-right text-[10px] font-semibold tabular-nums text-foreground">
                {fb.pct.toFixed(0)}%
              </span>
            </div>
          ))}
        </div>
      </Section>

      {/* ── Branch-point ── */}
      {bp_found_pct !== null && (
        <Section title="Détection du point de branchement (motif YNYURAY)">
          <div className="flex items-center gap-3">
            <Bar pct={bp_found_pct} className="bg-green-500" />
            <span className="text-[11px] font-semibold text-foreground tabular-nums">
              {bp_found_pct}%
            </span>
            <span className="text-[10px] text-muted-foreground">trouvés</span>
          </div>
        </Section>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mini helpers
// ---------------------------------------------------------------------------

function SummaryChip({ label, value }: { label: string; value: number }) {
  return (
    <div className="text-center px-3 py-2 rounded-lg bg-muted/40 border border-border">
      <p className="text-[9px] text-muted-foreground uppercase tracking-wide">{label}</p>
      <p className="text-base font-bold text-foreground tabular-nums">{value}</p>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-2">
        {title}
      </p>
      {children}
    </div>
  );
}
