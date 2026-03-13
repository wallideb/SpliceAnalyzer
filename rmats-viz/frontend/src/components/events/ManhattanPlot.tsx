"use client";

import { useMemo, useState, useCallback, useRef } from "react";
import { useT } from "@/contexts/LanguageContext";
import { EventDetailCard } from "./EventDetailCard";

// ── Types ────────────────────────────────────────────────────────────────────

export interface ManhattanPoint {
  id: string;
  event_type: string;
  gene_symbol?: string | null;
  chr?: string | null;
  position?: number | null;
  fdr?: number | null;
  inc_level_difference?: number | null;
}

export interface GeneMarker {
  symbol: string;
  ensembl_id?: string;
}

interface Props {
  data: ManhattanPoint[];
  loading?: boolean;
  /** Mutated gene symbols to highlight on the plot with vertical markers. */
  mutatedGenes?: GeneMarker[];
  /** Called when a data point is clicked — receives the event ID. */
  onEventClick?: (eventId: string) => void;
}

// ── Constants ────────────────────────────────────────────────────────────────

const EVENT_COLORS: Record<string, string> = {
  SE: "#3b82f6",   // blue
  RI: "#f59e0b",   // amber
  A3SS: "#10b981", // emerald
  A5SS: "#8b5cf6", // violet
  MXE: "#ef4444",  // red
};

const CHR_ORDER = [
  "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
  "11", "12", "13", "14", "15", "16", "17", "18", "19", "20",
  "21", "22", "X", "Y",
];

// Approximate human chromosome sizes (GRCh38, Mb)
const CHR_SIZES: Record<string, number> = {
  "1": 249, "2": 242, "3": 198, "4": 190, "5": 182, "6": 171,
  "7": 159, "8": 145, "9": 138, "10": 134, "11": 135, "12": 133,
  "13": 114, "14": 107, "15": 102, "16": 90, "17": 83, "18": 80,
  "19": 59, "20": 64, "21": 47, "22": 51, "X": 156, "Y": 57,
};

const MARGIN = { top: 20, right: 20, bottom: 50, left: 55 };
const WIDTH = 900;
const HEIGHT = 350;
const INNER_W = WIDTH - MARGIN.left - MARGIN.right;
const INNER_H = HEIGHT - MARGIN.top - MARGIN.bottom;
const GENOME_SIGNIFICANCE = -Math.log10(0.05);     // 1.301
const CHR_GAP = 4; // px gap between chromosomes

// ── Component ────────────────────────────────────────────────────────────────

export function ManhattanPlot({ data, loading, mutatedGenes = [], onEventClick }: Props) {
  const t = useT();
  const [visibleTypes, setVisibleTypes] = useState<Set<string>>(
    new Set(Object.keys(EVENT_COLORS)),
  );
  const [hovered, setHovered] = useState<ManhattanPoint | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });
  const [selected, setSelected] = useState<ManhattanPoint | null>(null);
  const [selectedAnchor, setSelectedAnchor] = useState({ x: 0, y: 0 });
  const plotContainerRef = useRef<HTMLDivElement>(null);

  // Normalize chromosome names (strip "chr" prefix)
  const normChr = useCallback((c: string) => c.replace(/^chr/i, ""), []);

  // Build chromosome layout: cumulative offsets for each chr
  const { chrOffsets, totalGenome, presentChrs } = useMemo(() => {
    const seen = new Set(data.map((d) => normChr(d.chr ?? "")));
    const present = CHR_ORDER.filter((c) => seen.has(c));
    let cum = 0;
    const offsets: Record<string, number> = {};
    for (const c of present) {
      offsets[c] = cum;
      cum += (CHR_SIZES[c] ?? 100) + CHR_GAP;
    }
    return { chrOffsets: offsets, totalGenome: cum, presentChrs: present };
  }, [data, normChr]);

  // Map points to pixel coords
  const points = useMemo(() => {
    const xScale = INNER_W / Math.max(totalGenome, 1);
    return data
      .filter((d) => d.chr && d.position != null && d.fdr != null && d.fdr > 0)
      .map((d) => {
        const c = normChr(d.chr!);
        const offset = chrOffsets[c];
        if (offset === undefined) return null;
        const genomicX = offset + (d.position! / 1e6); // Mb
        const negLogFdr = -Math.log10(d.fdr!);
        return {
          ...d,
          px: genomicX * xScale,
          py: negLogFdr,
          chrNorm: c,
        };
      })
      .filter(Boolean) as (ManhattanPoint & { px: number; py: number; chrNorm: string })[];
  }, [data, chrOffsets, totalGenome, normChr]);

  // Y-axis scale
  const maxY = useMemo(() => {
    const m = Math.max(...points.map((p) => p.py), GENOME_SIGNIFICANCE + 1);
    return Math.ceil(m);
  }, [points]);

  const yScale = useCallback(
    (val: number) => INNER_H - (val / maxY) * INNER_H,
    [maxY],
  );

  // Chromosome tick marks
  const chrTicks = useMemo(() => {
    const xScale = INNER_W / Math.max(totalGenome, 1);
    return presentChrs.map((c) => {
      const start = chrOffsets[c];
      const size = CHR_SIZES[c] ?? 100;
      return {
        chr: c,
        x: (start + size / 2) * xScale,
        width: size * xScale,
      };
    });
  }, [chrOffsets, presentChrs, totalGenome]);

  // Y-axis ticks
  const yTicks = useMemo(() => {
    const ticks: number[] = [];
    for (let i = 0; i <= maxY; i += Math.max(1, Math.floor(maxY / 6))) {
      ticks.push(i);
    }
    if (!ticks.includes(maxY)) ticks.push(maxY);
    return ticks;
  }, [maxY]);

  // Mutated gene position markers — compute median position for each gene from event data
  const geneMarkers = useMemo(() => {
    if (!mutatedGenes.length) return [];
    const xScale = INNER_W / Math.max(totalGenome, 1);
    const symbols = new Set(mutatedGenes.map((g) => g.symbol.toUpperCase()));
    // Group events by gene symbol
    const geneEvents: Record<string, { positions: number[]; chr: string }[]> = {};
    for (const d of data) {
      const sym = (d.gene_symbol ?? "").toUpperCase();
      if (!symbols.has(sym) || !d.chr || d.position == null) continue;
      if (!geneEvents[sym]) geneEvents[sym] = [];
      geneEvents[sym].push({ positions: [d.position], chr: normChr(d.chr) });
    }
    // Compute median position per gene per chromosome, pick most common chr
    return mutatedGenes
      .map((g) => {
        const sym = g.symbol.toUpperCase();
        const evts = geneEvents[sym];
        if (!evts || !evts.length) return null;
        // Group by chromosome, pick the one with the most events
        const byChr: Record<string, number[]> = {};
        for (const e of evts) {
          if (!byChr[e.chr]) byChr[e.chr] = [];
          byChr[e.chr].push(...e.positions);
        }
        const bestChr = Object.entries(byChr).sort((a, b) => b[1].length - a[1].length)[0];
        const chr = bestChr[0];
        const positions = bestChr[1].sort((a, b) => a - b);
        const median = positions[Math.floor(positions.length / 2)];
        const offset = chrOffsets[chr];
        if (offset === undefined) return null;
        const genomicX = offset + median / 1e6;
        return { symbol: g.symbol, px: genomicX * xScale, chr, nEvents: positions.length };
      })
      .filter(Boolean) as { symbol: string; px: number; chr: string; nEvents: number }[];
  }, [mutatedGenes, data, chrOffsets, totalGenome, normChr]);

  // Auto-labels: top 5 most significant events with distinct gene symbols
  const topLabels = useMemo(() => {
    const seen = new Set<string>();
    return [...points]
      .filter((p) => visibleTypes.has(p.event_type) && p.gene_symbol && p.py > GENOME_SIGNIFICANCE)
      .sort((a, b) => b.py - a.py)
      .filter((p) => {
        const sym = p.gene_symbol!.toUpperCase();
        if (seen.has(sym)) return false;
        seen.add(sym);
        return true;
      })
      .slice(0, 5);
  }, [points, visibleTypes]);

  const toggleType = useCallback((type: string) => {
    setVisibleTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  }, []);

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
        <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        {t("manhattan.loading")}
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-4">{t("manhattan.noData")}</p>
    );
  }

  const filteredPoints = points.filter((p) => visibleTypes.has(p.event_type));

  return (
    <div className="rounded-xl border border-border bg-card p-4 shadow-sm space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h3 className="text-sm font-bold text-foreground">{t("manhattan.title")}</h3>
        {/* Event type toggles */}
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(EVENT_COLORS).map(([type, color]) => {
            const active = visibleTypes.has(type);
            return (
              <button
                key={type}
                onClick={() => toggleType(type)}
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold border transition-colors ${
                  active
                    ? "bg-card border-border text-foreground"
                    : "bg-muted/40 border-transparent text-muted-foreground opacity-50"
                }`}
              >
                <span
                  className="w-2.5 h-2.5 rounded-full shrink-0"
                  style={{ backgroundColor: color, opacity: active ? 1 : 0.3 }}
                />
                {type}
              </button>
            );
          })}
        </div>
      </div>

      <div className="relative overflow-x-auto" ref={plotContainerRef}>
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="w-full max-w-[900px]"
          style={{ minWidth: 600 }}
        >
          <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
            {/* Alternating chromosome background bands */}
            {chrTicks.map(({ chr, x, width }, i) => (
              <rect
                key={chr}
                x={x - width / 2}
                y={0}
                width={width}
                height={INNER_H}
                fill={i % 2 === 0 ? "rgba(0,0,0,0.02)" : "rgba(0,0,0,0.06)"}
              />
            ))}

            {/* Significance threshold line */}
            <line
              x1={0}
              x2={INNER_W}
              y1={yScale(GENOME_SIGNIFICANCE)}
              y2={yScale(GENOME_SIGNIFICANCE)}
              stroke="#ef4444"
              strokeWidth={1}
              strokeDasharray="6,4"
              opacity={0.6}
            />
            <text
              x={INNER_W + 2}
              y={yScale(GENOME_SIGNIFICANCE) + 4}
              className="fill-red-500 dark:fill-red-400"
              fontSize={9}
              fontWeight={600}
            >
              FDR 0.05
            </text>

            {/* Significance band shading (above FDR 0.05 = significant region) */}
            <rect
              x={0}
              y={0}
              width={INNER_W}
              height={yScale(GENOME_SIGNIFICANCE)}
              fill="#ef4444"
              opacity={0.03}
            />

            {/* Data points */}
            {filteredPoints.map((p) => (
              <circle
                key={p.id}
                cx={p.px}
                cy={yScale(p.py)}
                r={hovered?.id === p.id ? 4.5 : 3}
                fill={EVENT_COLORS[p.event_type] ?? "#6b7280"}
                opacity={hovered?.id === p.id ? 1 : 0.7}
                stroke={hovered?.id === p.id ? "#000" : "none"}
                strokeWidth={0.5}
                onMouseEnter={(e) => {
                  setHovered(p);
                  const svg = e.currentTarget.closest("svg")!;
                  const rect = svg.getBoundingClientRect();
                  const svgPoint = svg.createSVGPoint();
                  svgPoint.x = e.clientX;
                  svgPoint.y = e.clientY;
                  setTooltipPos({
                    x: e.clientX - rect.left,
                    y: e.clientY - rect.top,
                  });
                }}
                onMouseLeave={() => setHovered(null)}
                onClick={(e) => {
                  onEventClick?.(p.id);
                  const rect = plotContainerRef.current?.getBoundingClientRect();
                  if (rect) {
                    setSelected(p);
                    setSelectedAnchor({
                      x: e.clientX - rect.left,
                      y: e.clientY - rect.top,
                    });
                  }
                }}
                className="cursor-pointer transition-all"
              />
            ))}

            {/* Auto gene labels for top significant events */}
            {topLabels.map((p, i) => (
              <g key={`label-${p.id}`}>
                <line
                  x1={p.px}
                  y1={yScale(p.py) - 4}
                  x2={p.px}
                  y2={yScale(p.py) - 12 - i * 2}
                  stroke="hsl(var(--muted-foreground))"
                  strokeWidth={0.5}
                  opacity={0.6}
                />
                <text
                  x={p.px}
                  y={yScale(p.py) - 14 - i * 2}
                  textAnchor="middle"
                  fontSize={7}
                  fontWeight={600}
                  fontStyle="italic"
                  className="fill-foreground"
                >
                  {p.gene_symbol}
                </text>
              </g>
            ))}

            {/* Mutated gene position markers */}
            {geneMarkers.map((gm, i) => (
              <g key={`gene-${gm.symbol}`}>
                <line
                  x1={gm.px}
                  y1={0}
                  x2={gm.px}
                  y2={INNER_H}
                  stroke="#f59e0b"
                  strokeWidth={1.5}
                  strokeDasharray="4,3"
                  opacity={0.7}
                />
                <rect
                  x={gm.px - 2}
                  y={-14 - i * 14}
                  width={gm.symbol.length * 7 + 8}
                  height={13}
                  rx={3}
                  fill="var(--svg-gene-marker-bg)"
                  stroke="#f59e0b"
                  strokeWidth={0.8}
                  opacity={0.95}
                />
                <text
                  x={gm.px + 2}
                  y={-5 - i * 14}
                  fontSize={8}
                  fontWeight={700}
                  fill="var(--svg-gene-marker-text)"
                  fontFamily="sans-serif"
                >
                  {gm.symbol}
                </text>
              </g>
            ))}

            {/* X-axis: chromosome labels */}
            {chrTicks.map(({ chr, x }) => (
              <text
                key={chr}
                x={x}
                y={INNER_H + 18}
                textAnchor="middle"
                fontSize={10}
                className="fill-muted-foreground"
              >
                {chr}
              </text>
            ))}

            {/* X-axis label */}
            <text
              x={INNER_W / 2}
              y={INNER_H + 40}
              textAnchor="middle"
              fontSize={11}
              fontWeight={600}
              className="fill-foreground"
            >
              {t("manhattan.xAxis")}
            </text>

            {/* Y-axis ticks */}
            {yTicks.map((tick) => (
              <g key={tick}>
                <line
                  x1={-4}
                  x2={INNER_W}
                  y1={yScale(tick)}
                  y2={yScale(tick)}
                  stroke="currentColor"
                  strokeWidth={0.3}
                  opacity={0.15}
                />
                <text
                  x={-8}
                  y={yScale(tick) + 3.5}
                  textAnchor="end"
                  fontSize={10}
                  className="fill-muted-foreground"
                >
                  {tick}
                </text>
              </g>
            ))}

            {/* Y-axis label */}
            <text
              x={0}
              y={0}
              textAnchor="middle"
              fontSize={11}
              fontWeight={600}
              className="fill-foreground"
              transform={`translate(${-40},${INNER_H / 2}) rotate(-90)`}
            >
              {t("manhattan.yAxis")}
            </text>

            {/* Axes */}
            <line x1={0} x2={INNER_W} y1={INNER_H} y2={INNER_H} stroke="currentColor" strokeWidth={0.5} opacity={0.3} />
            <line x1={0} x2={0} y1={0} y2={INNER_H} stroke="currentColor" strokeWidth={0.5} opacity={0.3} />
          </g>
        </svg>

        {/* Tooltip */}
        {hovered && (
          <div
            className="absolute pointer-events-none z-10 bg-popover border border-border rounded-lg shadow-lg px-3 py-2 text-xs space-y-0.5"
            style={{
              left: Math.min(tooltipPos.x + 12, (typeof window !== "undefined" ? 800 : 800)),
              top: tooltipPos.y - 60,
            }}
          >
            <div className="font-bold text-foreground">
              {hovered.gene_symbol ?? "—"}{" "}
              <span className="font-normal text-muted-foreground">({hovered.event_type})</span>
            </div>
            <div className="text-muted-foreground">
              chr{hovered.chr?.replace(/^chr/i, "")}:{hovered.position?.toLocaleString()}
            </div>
            <div>
              FDR: <span className="font-semibold">{hovered.fdr?.toExponential(2)}</span>
            </div>
            {hovered.inc_level_difference != null && (
              <div>
                ΔPSI: <span className="font-semibold">{hovered.inc_level_difference.toFixed(3)}</span>
              </div>
            )}
          </div>
        )}

        {/* Event detail card (click) */}
        {selected && !hovered && (
          <EventDetailCard
            event={selected}
            anchor={selectedAnchor}
            onClose={() => setSelected(null)}
            onViewInTable={(ev) => {
              onEventClick?.(ev.id);
              setSelected(null);
            }}
          />
        )}
      </div>

      <p className="text-[10px] text-muted-foreground">
        {t("manhattan.description", { n: filteredPoints.length })}
        {" · "}
        <span className="italic">{t("manhattan.clickHint")}</span>
      </p>
    </div>
  );
}
