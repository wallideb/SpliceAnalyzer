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

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getSplicePatterns, computeSpliceFeatures } from "@/lib/api/splice";
import { getPatternComparison } from "@/lib/api/deep-analyses";
import type { GroupPatternStats, StatTestResult } from "@/lib/api/deep-analyses";
import { ScienceNote } from "@/components/ScienceNote";
import { useT } from "@/contexts/LanguageContext";
import { formatDeltaPSI } from "@/lib/utils";
import type { SplicingEvent } from "@/types/event";
import type { ExonSizeStats } from "@/types/splice";
import { ConsensusLogoPanel } from "./ConsensusLogoPanel";
import { ConsensusExonView } from "./ConsensusExonView";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface MotifPatternPanelProps {
  events: SplicingEvent[];
  analysisId: string;
  /** When set, restricts patterns to significant events of this deep analysis. */
  deepAnalysisId?: string;
  /** Pre-set thresholds from the deep analysis (disables threshold controls). */
  fdrThreshold?: number;
  deltaPsiMin?: number;
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
  const t = useT();
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
        aria-label={t("motifPanel.histogramAriaLabel")}
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
                onMouseEnter={() =>
                  setHoveredBin({ bin: d.bin, count: d.count, x: x + barW / 2, y })
                }
                onMouseLeave={() => setHoveredBin(null)}
              >
                <title>{t("motifPanel.histogramBinTitle", { start: d.bin, end: d.bin + 25, count: d.count })}</title>
              </rect>
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
          {t("motifPanel.histogramAxisTitle")}
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
              {t("motifPanel.histogramMeanLabel", { n: Math.round(mean) })}
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
              {t("motifPanel.histogramMedianLabel", { n: Math.round(median) })}
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
              {hoveredBin.bin}–{hoveredBin.bin + 25} nt : <strong>{hoveredBin.count}</strong> {t("motifPanel.histogramTooltipEvents")}
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
          {t("motifPanel.histogramLegendMean")}
        </span>
        <span className="flex items-center gap-1">
          <svg width="18" height="8" className="inline-block">
            <line x1="0" y1="4" x2="18" y2="4" stroke="#f97316" strokeWidth="1.5" strokeDasharray="3 2" />
          </svg>
          {t("motifPanel.histogramLegendMedian")}
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

// FDR preset options
const FDR_OPTIONS = [0.001, 0.01, 0.05, 0.1, 0.2] as const;
// |ΔΨ| preset options
const DPSI_OPTIONS = [0, 0.05, 0.1, 0.2, 0.3] as const;

export function MotifPatternPanel({ events, analysisId, deepAnalysisId, fdrThreshold: propFdr, deltaPsiMin: propDpsi }: MotifPatternPanelProps) {
  const t = useT();
  const qc = useQueryClient();

  // Significance threshold state (only used when not in deep-analysis mode)
  const [localFdr, setLocalFdr] = useState<number>(0.05);
  const [localDpsi, setLocalDpsi] = useState<number>(0.05);
  const [showThresholds, setShowThresholds] = useState(false);

  const fdrThreshold = propFdr ?? localFdr;
  const absDeltaPsiMin = propDpsi ?? localDpsi;
  const isDeepMode = !!deepAnalysisId;

  const seCount = events.filter((e) => e.event_type === "SE").length;
  const nonSeCount = events.length - seCount;

  // After triggering compute (which returns 202 immediately), poll until data appears.
  const [isPolling, setIsPolling] = useState(false);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["splice-patterns", analysisId, fdrThreshold, absDeltaPsiMin, deepAnalysisId],
    queryFn: () => getSplicePatterns(analysisId, fdrThreshold, absDeltaPsiMin, deepAnalysisId),
    enabled: !!analysisId,
    staleTime: 10 * 60 * 1000,
    retry: false,
    // Poll every 4 s while waiting for background computation to finish
    refetchInterval: isPolling ? 4_000 : false,
    // Stop polling once data arrives
    refetchIntervalInBackground: false,
  });

  // Pattern comparison data (sig vs non-sig) — only in deep-analysis mode
  const { data: cmpData } = useQuery({
    queryKey: ["pattern-comparison", deepAnalysisId],
    queryFn: () => getPatternComparison(deepAnalysisId!),
    enabled: isDeepMode,
    staleTime: 5 * 60 * 1000,
  });

  // Stop polling once we have data (must be in useEffect, not render body)
  useEffect(() => {
    if (isPolling && data) setIsPolling(false);
  }, [isPolling, data]);

  const compute = useMutation({
    mutationFn: () => computeSpliceFeatures(analysisId),
    onSuccess: () => {
      // Compute now returns 202 immediately; poll until background task finishes
      setIsPolling(true);
    },
  });

  // ── Polling (background compute running) ─────────────────────────────────
  if (isPolling && !data) {
    return (
      <div className="flex flex-col items-center gap-4 py-10 text-center">
        <svg className="animate-spin w-10 h-10 text-blue-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        <div>
          <p className="text-sm font-semibold text-foreground">{t("motifPanel.computing")}</p>
          <p className="text-xs text-muted-foreground mt-1">{t("motifPanel.computingDesc")}</p>
        </div>
      </div>
    );
  }

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
            {t("motifPanel.notComputed")}
          </p>
          <p className="text-xs text-muted-foreground max-w-xs leading-relaxed">
            {t("motifPanel.notComputedDesc", { n: seCount })}
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
          {compute.isPending ? t("motifPanel.computing") : t("motifPanel.computeBtn")}
        </button>
        {compute.isError && (
          <p className="text-xs text-red-500">{t("motifPanel.computeError")}</p>
        )}
      </div>
    );
  }

  // ── Computed ─────────────────────────────────────────────────────────────
  const { exon_sizes, donor_sites, acceptor_sites, ppt, frame, bp_found_pct } = data;

  // Frame totals for bar widths
  const frameTotal = (frame.in_frame + frame.frameshift + frame.non_coding + frame.unknown) || 1;
  const frameBars = [
    { label: "In-frame",                              value: frame.in_frame,   pct: (frame.in_frame / frameTotal) * 100,   color: "bg-green-500" },
    { label: "Frameshift",                            value: frame.frameshift,  pct: (frame.frameshift / frameTotal) * 100,  color: "bg-red-500" },
    { label: t("motifPanel.frameLabelNonCoding"),     value: frame.non_coding,  pct: (frame.non_coding / frameTotal) * 100,  color: "bg-slate-400" },
    { label: t("motifPanel.frameLabelUnknown"),       value: frame.unknown,     pct: (frame.unknown / frameTotal) * 100,     color: "bg-muted-foreground/30" },
  ];

  const sigPct = data.n_se_events > 0
    ? Math.round((data.n_significant / data.n_se_events) * 100)
    : 0;

  return (
    <div className="space-y-6 text-xs">

      {/* ── Thresholds settings bar ── */}
      <div className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg bg-muted/30 border border-border">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
            {t("motifPanel.thresholds")}
          </span>
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 text-blue-700 dark:text-blue-300 text-[11px] font-semibold">
            FDR ≤ {fdrThreshold}
          </span>
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-violet-50 dark:bg-violet-950/30 border border-violet-200 dark:border-violet-800 text-violet-700 dark:text-violet-300 text-[11px] font-semibold">
            |ΔΨ| ≥ {absDeltaPsiMin}
          </span>
          {isDeepMode && (
            <span className="text-[10px] text-green-600 dark:text-green-400 font-medium">
              ({t("motifPanel.significantOnly")})
            </span>
          )}
        </div>
        {!isDeepMode && (
          <button
            type="button"
            onClick={() => setShowThresholds((v) => !v)}
            className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-semibold rounded-md border border-border hover:bg-muted/60 transition-colors text-muted-foreground hover:text-foreground"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            {t("motifPanel.modify")}
          </button>
        )}
      </div>

      {/* ── Threshold settings panel (only in standalone mode) ── */}
      {!isDeepMode && showThresholds && (
        <div className="p-4 rounded-xl border border-border bg-card shadow-sm space-y-4">
          <p className="text-[11px] font-bold text-foreground">
            {t("motifPanel.thresholdsTitle")}
          </p>
          <p className="text-[10px] text-muted-foreground leading-relaxed">
            {t("motifPanel.thresholdsDesc")}
          </p>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">
                FDR ≤
              </label>
              <div className="flex flex-wrap gap-1.5">
                {FDR_OPTIONS.map((v) => (
                  <button
                    key={v}
                    type="button"
                    onClick={() => setLocalFdr(v)}
                    className={`px-2 py-1 rounded text-[11px] font-semibold border transition-colors ${
                      fdrThreshold === v
                        ? "bg-blue-600 text-white border-blue-600"
                        : "bg-card border-border text-muted-foreground hover:bg-muted"
                    }`}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="block text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">
                |ΔΨ| ≥
              </label>
              <div className="flex flex-wrap gap-1.5">
                {DPSI_OPTIONS.map((v) => (
                  <button
                    key={v}
                    type="button"
                    onClick={() => setLocalDpsi(v)}
                    className={`px-2 py-1 rounded text-[11px] font-semibold border transition-colors ${
                      absDeltaPsiMin === v
                        ? "bg-violet-600 text-white border-violet-600"
                        : "bg-card border-border text-muted-foreground hover:bg-muted"
                    }`}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setShowThresholds(false)}
            className="text-[11px] text-muted-foreground hover:text-foreground transition-colors"
          >
            {t("motifPanel.close")}
          </button>
        </div>
      )}

      {/* ── 2C — Consensus ExonDiagram (figure principale) ── */}
      <Section title={t("motifPanel.sectionConsensus")}>
        <ConsensusExonView data={data} />
      </Section>

      {/* ── Summary chips ── */}
      <div className="flex flex-wrap gap-3 items-start">
        <SummaryChip label={t("motifPanel.summarySeEvents")} value={data.n_se_events} />
        <SummaryChip label={t("motifPanel.summaryAnalyzed")} value={data.n_analyzed} />
        {/* Significance breakdown */}
        <div className="text-center px-3 py-2 rounded-lg bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800">
          <p className="text-[9px] text-green-700 dark:text-green-400 uppercase tracking-wide font-semibold">{t("motifPanel.significantChip")}</p>
          <p className="text-base font-bold text-green-700 dark:text-green-300 tabular-nums">
            {data.n_significant}
            <span className="text-[10px] font-normal text-green-600 dark:text-green-400 ml-1">({sigPct}%)</span>
          </p>
        </div>
        <div className="text-center px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-700/30 border border-slate-200 dark:border-slate-600">
          <p className="text-[9px] text-muted-foreground uppercase tracking-wide font-semibold">{t("motifPanel.notSignificantChip")}</p>
          <p className="text-base font-bold text-muted-foreground tabular-nums">{data.n_not_significant}</p>
        </div>
        {!data.fasta_available && (
          <span className="self-center text-[10px] text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded px-2 py-1">
            {t("motifPanel.fastaNotAvailable")}
          </span>
        )}
        {nonSeCount > 0 && (
          <span className="self-center text-[10px] text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800 rounded px-2 py-1">
            {t("motifPanel.nonSeNotice", { n: nonSeCount })}
          </span>
        )}
      </div>

      {/* ── Exon size distribution ── */}
      {exon_sizes && (
        <Section title={t("motifPanel.sectionExonSizes")}>
          {exon_sizes.mean !== null && (
            <div className="flex gap-4 mb-2 text-[10px] text-muted-foreground">
              <span>{t("motifPanel.statMean")} <strong className="text-foreground">{exon_sizes.mean} nt</strong></span>
              <span>{t("motifPanel.statMedian")} <strong className="text-foreground">{exon_sizes.median} nt</strong></span>
              <span>Min <strong className="text-foreground">{exon_sizes.min}</strong></span>
              <span>Max <strong className="text-foreground">{exon_sizes.max}</strong></span>
            </div>
          )}
          <ExonSizeHistogram stats={exon_sizes} />
        </Section>
      )}

      {/* ── 5'SS donor logo ── */}
      {donor_sites && donor_sites.pwm.length > 0 && (
        <Section title={t("motifPanel.sectionDonor", { n: donor_sites.n_sequences, pct: donor_sites.pct_canonical })}>
          {donor_sites.consensus && (
            <p className="text-[10px] text-muted-foreground mb-1">
              {t("motifPanel.iupacConsensus")} <code className="font-mono font-bold text-foreground">{donor_sites.consensus}</code>
            </p>
          )}
          <ConsensusLogoPanel
            pwm={donor_sites.pwm}
            title="Logo 5'SS (9 nt)"
            startPosition={-3}
            skipZero
            canonicalPositions={[1, 2]}
            id="logo-donor"
            nSequences={donor_sites.n_sequences}
          />
        </Section>
      )}

      {/* ── 3'SS acceptor logo ── */}
      {acceptor_sites && acceptor_sites.pwm.length > 0 && (
        <Section title={t("motifPanel.sectionAcceptor", { n: acceptor_sites.n_sequences, pct: acceptor_sites.pct_canonical })}>
          {acceptor_sites.consensus && (
            <p className="text-[10px] text-muted-foreground mb-1">
              {t("motifPanel.iupacConsensus")} <code className="font-mono font-bold text-foreground">{acceptor_sites.consensus}</code>
            </p>
          )}
          <ConsensusLogoPanel
            pwm={acceptor_sites.pwm}
            title="Logo 3'SS (23 nt)"
            startPosition={-20}
            skipZero
            canonicalPositions={[-2, -1]}
            id="logo-acceptor"
            nSequences={acceptor_sites.n_sequences}
          />
        </Section>
      )}

      {/* ── PPT score distribution ── */}
      {ppt && ppt.scores.length > 0 && (
        <Section title={t("motifPanel.sectionPpt", { pct: ppt.mean_score !== null ? Math.round(ppt.mean_score * 100) : "—", run: ppt.mean_longest_run ?? "—" })}>
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
      <Section title={t("motifPanel.sectionFrame")}>
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
            <span className="text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">{t("motifPanel.frameLabelNonCoding")}</span>
          </span>
          {frame.unknown > 0 && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border bg-muted border-border">
              <span className="text-muted-foreground text-base font-bold tabular-nums">{frame.unknown}</span>
              <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">{t("motifPanel.frameLabelUnknown")}</span>
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
        <Section title={t("motifPanel.sectionBp")}>
          <div className="flex items-center gap-3">
            <Bar pct={bp_found_pct} className="bg-green-500" />
            <span className="text-[11px] font-semibold text-foreground tabular-nums">
              {bp_found_pct}%
            </span>
            <span className="text-[10px] text-muted-foreground">{t("motifPanel.bpDetected")}</span>
          </div>
        </Section>
      )}

      {/* ── Sig vs Non-sig feature comparison table (deep-analysis only) ── */}
      {cmpData && <FeatureComparisonSection data={cmpData} t={t} />}

      <ScienceNote
        title={t("scienceNotes.motifPattern.title")}
        body={t("scienceNotes.motifPattern.body")}
        refs={["sequence_logos", "splice_sites", "ppt", "branch_point"]}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Feature comparison table + frame breakdown (sig vs non-sig)
// ---------------------------------------------------------------------------

function FeatureComparisonSection({
  data,
  t,
}: {
  data: import("@/lib/api/deep-analyses").PatternComparisonResponse;
  t: ReturnType<typeof useT>;
}) {
  const { significant: sig, not_significant: nonsig, statistical_tests: tests } = data;
  const testMap = new Map<string, StatTestResult>();
  for (const t2 of tests ?? []) testMap.set(t2.feature, t2);
  const p = (key: string) => testMap.get(key);

  return (
    <>
      {/* Comparison table */}
      <Section title={t("motifPanel.sectionComparison")}>
        <div className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 border-b border-border">
              <tr>
                <th className="px-3 py-2.5 text-xs font-semibold text-left text-muted-foreground w-1/4">Feature</th>
                <th className="px-3 py-2.5 text-xs font-bold text-center text-green-700 dark:text-green-400">
                  {t("deepAnalysis.significant")} <span className="font-normal opacity-70">({sig.n_events})</span>
                </th>
                <th className="px-3 py-2.5 text-xs font-bold text-center text-slate-500">
                  {t("deepAnalysis.notSignificant")} <span className="font-normal opacity-70">({nonsig.n_events})</span>
                </th>
                <th className="px-3 py-2.5 text-xs font-semibold text-center text-muted-foreground w-[90px]">p-value</th>
              </tr>
            </thead>
            <tbody>
              <CmpRow label="SE events with features" sigVal={sig.n_se_with_features} nonsigVal={nonsig.n_se_with_features} />
              <CmpRow label="Mean exon size" sigVal={sig.exon_size_mean != null ? `${sig.exon_size_mean} nt` : null} nonsigVal={nonsig.exon_size_mean != null ? `${nonsig.exon_size_mean} nt` : null} pValue={p("exon_size")?.p_value} testName={p("exon_size")?.test_name} />
              <CmpRow label="Median exon size" sigVal={sig.exon_size_median != null ? `${sig.exon_size_median} nt` : null} nonsigVal={nonsig.exon_size_median != null ? `${nonsig.exon_size_median} nt` : null} />
              <CmpRow label="Canonical GT (5'SS)" sigVal={sig.pct_canonical_gt} nonsigVal={nonsig.pct_canonical_gt} format="pct" pValue={p("canonical_gt")?.p_value} testName={p("canonical_gt")?.test_name} />
              <CmpRow label="Canonical AG (3'SS)" sigVal={sig.pct_canonical_ag} nonsigVal={nonsig.pct_canonical_ag} format="pct" pValue={p("canonical_ag")?.p_value} testName={p("canonical_ag")?.test_name} />
              <CmpRow label="Mean PPT score" sigVal={sig.ppt_mean_score != null ? `${Math.round(sig.ppt_mean_score * 100)}%` : null} nonsigVal={nonsig.ppt_mean_score != null ? `${Math.round(nonsig.ppt_mean_score * 100)}%` : null} pValue={p("ppt_score")?.p_value} testName={p("ppt_score")?.test_name} />
              <CmpRow label="In-frame" sigVal={sig.frame_in_frame} nonsigVal={nonsig.frame_in_frame} pValue={p("in_frame_pct")?.p_value} testName={p("in_frame_pct")?.test_name} />
              <CmpRow label="Frameshift" sigVal={sig.frame_frameshift} nonsigVal={nonsig.frame_frameshift} />
              <CmpRow label="Non-coding" sigVal={sig.frame_non_coding} nonsigVal={nonsig.frame_non_coding} />
              <CmpRow label="Branch point found" sigVal={sig.bp_found_pct} nonsigVal={nonsig.bp_found_pct} format="pct" pValue={p("bp_found")?.p_value} testName={p("bp_found")?.test_name} />
              <CmpRow label="Mean ΔΨ" sigVal={sig.mean_delta_psi != null ? formatDeltaPSI(sig.mean_delta_psi) : null} nonsigVal={nonsig.mean_delta_psi != null ? formatDeltaPSI(nonsig.mean_delta_psi) : null} pValue={p("mean_delta_psi")?.p_value} testName={p("mean_delta_psi")?.test_name} />
            </tbody>
          </table>
          {tests && tests.length > 0 && (
            <div className="px-4 py-3 border-t border-border flex items-center gap-4 text-[10px] text-muted-foreground">
              <span>p-value:</span>
              <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-full bg-green-500" /> &lt; 0.01</span>
              <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-full bg-amber-500" /> &lt; 0.05</span>
              <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-full bg-slate-400" /> n.s.</span>
              <span className="ml-auto italic">Hover p-value for test name</span>
            </div>
          )}
        </div>
      </Section>

      {/* Frame breakdown side-by-side */}
      <Section title={t("motifPanel.sectionFrameComparison")}>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <CmpFrameBar stats={sig} label={`${t("deepAnalysis.significant")} (${sig.n_se_with_features})`} />
          <CmpFrameBar stats={nonsig} label={`${t("deepAnalysis.notSignificant")} (${nonsig.n_se_with_features})`} />
        </div>
        {p("in_frame_pct") && p("in_frame_pct")!.p_value != null && (
          <div className="flex items-center justify-center gap-2 py-1.5 px-3 rounded-lg bg-muted/40 border border-border text-[10px] mt-3">
            <span className="text-muted-foreground">{p("in_frame_pct")!.test_name}:</span>
            <span className={`font-mono font-semibold ${
              p("in_frame_pct")!.p_value! < 0.01 ? "text-green-600 dark:text-green-400" :
              p("in_frame_pct")!.p_value! < 0.05 ? "text-amber-600 dark:text-amber-400" :
              "text-muted-foreground"
            }`}>
              p = {p("in_frame_pct")!.p_value! < 0.0001 ? p("in_frame_pct")!.p_value!.toExponential(2) : p("in_frame_pct")!.p_value!.toFixed(4)}
            </span>
          </div>
        )}
      </Section>
    </>
  );
}

/** Comparison table row */
function CmpRow({
  label, sigVal, nonsigVal, format = "default", pValue, testName,
}: {
  label: string;
  sigVal: string | number | null;
  nonsigVal: string | number | null;
  format?: "default" | "pct";
  pValue?: number | null;
  testName?: string;
}) {
  const fmt = (v: string | number | null) => {
    if (v === null || v === undefined) return "—";
    if (format === "pct" && typeof v === "number") return `${v}%`;
    if (typeof v === "number") return v.toLocaleString();
    return v;
  };
  return (
    <tr className="border-b border-border/50">
      <td className="px-3 py-2 text-xs text-muted-foreground font-medium">{label}</td>
      <td className="px-3 py-2 text-xs text-foreground font-semibold tabular-nums text-center">{fmt(sigVal)}</td>
      <td className="px-3 py-2 text-xs text-muted-foreground tabular-nums text-center">{fmt(nonsigVal)}</td>
      {pValue !== undefined ? (
        <td className={`px-3 py-2 text-[10px] tabular-nums text-center font-semibold ${
          pValue !== null && pValue < 0.01 ? "text-green-600 dark:text-green-400" :
          pValue !== null && pValue < 0.05 ? "text-amber-600 dark:text-amber-400" :
          "text-muted-foreground"
        }`} title={testName}>
          {pValue !== null ? pValue.toFixed(4) : "—"}
        </td>
      ) : <td className="px-3 py-2" />}
    </tr>
  );
}

/** Comparison frame bar */
function CmpFrameBar({ stats, label }: { stats: GroupPatternStats; label: string }) {
  const total = stats.frame_in_frame + stats.frame_frameshift + stats.frame_non_coding;
  if (total === 0) return <p className="text-[10px] text-muted-foreground">No data</p>;
  const pctIF = (stats.frame_in_frame / total) * 100;
  const pctFS = (stats.frame_frameshift / total) * 100;
  const pctNC = (stats.frame_non_coding / total) * 100;
  return (
    <div>
      <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">{label}</p>
      <div className="flex h-4 rounded-full overflow-hidden border border-border">
        {pctIF > 0 && <div className="bg-green-500 h-full" style={{ width: `${pctIF}%` }} title={`In-frame: ${stats.frame_in_frame} (${pctIF.toFixed(0)}%)`} />}
        {pctFS > 0 && <div className="bg-red-500 h-full" style={{ width: `${pctFS}%` }} title={`Frameshift: ${stats.frame_frameshift} (${pctFS.toFixed(0)}%)`} />}
        {pctNC > 0 && <div className="bg-slate-400 h-full" style={{ width: `${pctNC}%` }} title={`Non-coding: ${stats.frame_non_coding} (${pctNC.toFixed(0)}%)`} />}
      </div>
      <div className="flex gap-3 mt-1 text-[9px] text-muted-foreground">
        <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-sm bg-green-500" /> In-frame {pctIF.toFixed(0)}%</span>
        <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-sm bg-red-500" /> Frameshift {pctFS.toFixed(0)}%</span>
        <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-sm bg-slate-400" /> Non-coding {pctNC.toFixed(0)}%</span>
      </div>
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
