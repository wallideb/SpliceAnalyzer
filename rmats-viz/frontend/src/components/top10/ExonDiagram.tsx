"use client";

/**
 * ExonDiagram — Publication-style SVG exon-skipping diagram
 * ==========================================================
 * Renders a schematic of a skipped exon (SE) event, including:
 *  - Upstream and downstream flanking exons
 *  - Intron lines with chevron (V-notch) in the centre
 *  - Central skipped exon rectangle
 *  - A Bezier arc above representing the skipping junction
 *  - Statistical labels (FDR, ΔΨ, p-value) near the arc apex
 *  - Intron and exon sizes in nucleotides
 *  - Warnings for non-canonical splice sites (non-GT/AG)
 *
 * No external dependencies — pure React + SVG.
 */

import React from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ExonDiagramProps {
  exonSize: number | null;
  upstreamIntronSize: number | null;
  downstreamIntronSize: number | null;
  incLevelDifference: number | null; // ΔΨ — drives arc colour + width
  fdr: number | null;
  pValue: number | null;
  strand: string | null;
  donorIsGt?: boolean | null;
  acceptorIsAg?: boolean | null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtPval(v: number | null): string {
  if (v === null) return "—";
  if (v < 0.001) return v.toExponential(1);
  return v.toFixed(3);
}

function fmtDelta(v: number | null): string {
  if (v === null) return "—";
  const s = v.toFixed(2);
  return v >= 0 ? `+${s}` : s;
}

function fmtSize(v: number | null): string {
  if (v === null) return "?";
  return v.toLocaleString();
}

// ---------------------------------------------------------------------------
// Layout constants (all in SVG user units)
// ---------------------------------------------------------------------------

const W = 500;
const H = 140;

// Vertical positions
const EXON_Y = 68;        // top of exon rectangles
const EXON_H = 22;        // height of exon rectangles
const INTRON_Y = EXON_Y + EXON_H / 2; // centre of introns (mid-height of exons)
const LABEL_Y = EXON_Y + EXON_H + 13; // size labels below exons/introns

// Horizontal layout
const FLANK_W = 46;       // width of flanking exons
const SKIP_W = 80;        // width of skipped exon
const MARGIN = 18;        // left/right margin
const GAP = 14;           // gap between flanking exon and intron line start

// Derived x positions
const LEFT_EXON_X = MARGIN;
const LEFT_EXON_RIGHT = LEFT_EXON_X + FLANK_W;
const RIGHT_EXON_X = W - MARGIN - FLANK_W;
const RIGHT_EXON_LEFT = RIGHT_EXON_X;

// Intron lines start/end
const LEFT_INTRON_START = LEFT_EXON_RIGHT;
const RIGHT_INTRON_END = RIGHT_EXON_LEFT;

// Skipped exon centred between the two introns
const SKIP_X = (W - SKIP_W) / 2;
const SKIP_RIGHT = SKIP_X + SKIP_W;

// Intron left spans from LEFT_INTRON_START to SKIP_X
// Intron right spans from SKIP_RIGHT to RIGHT_INTRON_END

// Arc control points
const ARC_TOP_Y = 14;     // apex of the skip arc

// Colours
const COLOR_FLANK = "#94a3b8";   // slate-400
const COLOR_SKIP  = "#6366f1";   // indigo-500
const COLOR_BLUE  = "#3b82f6";   // blue-500 — skipping (ΔΨ < 0)
const COLOR_RED   = "#ef4444";   // red-500  — inclusion (ΔΨ > 0)
const COLOR_WARN  = "#f59e0b";   // amber-500 — non-canonical
const COLOR_TEXT_MUTED = "#94a3b8";
const COLOR_TEXT_MAIN  = "#e2e8f0";

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** A horizontal intron line with a downward V notch in the middle */
function IntronLine({
  x1,
  x2,
  y,
  size,
  labelAlign = "center",
}: {
  x1: number;
  x2: number;
  y: number;
  size: number | null;
  labelAlign?: "left" | "center" | "right";
}) {
  const mid = (x1 + x2) / 2;
  const notchDepth = 6;
  const d = `M ${x1} ${y} L ${mid} ${y + notchDepth} L ${x2} ${y}`;

  const lx =
    labelAlign === "left"
      ? x1
      : labelAlign === "right"
      ? x2
      : mid;
  const anchor =
    labelAlign === "left" ? "start" : labelAlign === "right" ? "end" : "middle";

  return (
    <g>
      <path d={d} stroke={COLOR_FLANK} strokeWidth={1.5} fill="none" />
      {size !== null && (
        <text
          x={lx}
          y={LABEL_Y + 2}
          textAnchor={anchor}
          fontSize={9}
          fill={COLOR_TEXT_MUTED}
          fontFamily="monospace"
        >
          {fmtSize(size)} nt
        </text>
      )}
    </g>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ExonDiagram({
  exonSize,
  upstreamIntronSize,
  downstreamIntronSize,
  incLevelDifference,
  fdr,
  pValue,
  strand,
  donorIsGt,
  acceptorIsAg,
}: ExonDiagramProps) {
  // Arc visual properties
  const delta = incLevelDifference ?? 0;
  const arcColor = delta < 0 ? COLOR_BLUE : COLOR_RED;
  const arcWidth = Math.max(1.5, Math.min(4.5, 1.5 + Math.abs(delta) * 5));
  const arcDashed = fdr !== null && fdr > 0.05;

  // Arc: cubic Bezier from left flanking exon right edge to right flanking exon left edge
  // passing through apex at ARC_TOP_Y
  const arcStartX = LEFT_EXON_RIGHT;
  const arcStartY = EXON_Y;
  const arcEndX   = RIGHT_EXON_LEFT;
  const arcEndY   = EXON_Y;
  const arcMidX   = W / 2;

  // Control points for a smooth arch
  const cp1x = arcStartX + (arcMidX - arcStartX) * 0.45;
  const cp1y = ARC_TOP_Y;
  const cp2x = arcMidX + (arcEndX - arcMidX) * 0.55;
  const cp2y = ARC_TOP_Y;

  const arcPath = `M ${arcStartX} ${arcStartY} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${arcEndX} ${arcEndY}`;

  // Stats label
  const hasStats = fdr !== null || incLevelDifference !== null || pValue !== null;
  const statsLine = [
    fdr !== null ? `FDR: ${fmtPval(fdr)}` : null,
    incLevelDifference !== null ? `ΔΨ: ${fmtDelta(incLevelDifference)}` : null,
    pValue !== null ? `p: ${fmtPval(pValue)}` : null,
  ]
    .filter(Boolean)
    .join("  |  ");

  // Donor/acceptor warning flags
  const warnDonor    = donorIsGt === false;
  const warnAcceptor = acceptorIsAg === false;

  return (
    <div className="w-full overflow-x-auto" title="Schéma exon sauté">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: "100%", maxWidth: W, minWidth: 280, display: "block" }}
        aria-label="Diagramme exon sauté"
        role="img"
      >
        {/* ── Arc de saut ── */}
        <path
          d={arcPath}
          stroke={arcColor}
          strokeWidth={arcWidth}
          fill="none"
          strokeDasharray={arcDashed ? "5 3" : undefined}
          strokeLinecap="round"
        />

        {/* ── Stats label at arc apex ── */}
        {hasStats && (
          <text
            x={arcMidX}
            y={ARC_TOP_Y - 3}
            textAnchor="middle"
            fontSize={8.5}
            fill={arcColor}
            fontFamily="monospace"
            fontWeight="600"
          >
            {statsLine}
          </text>
        )}

        {/* ── Exon flanquant gauche ── */}
        <rect
          x={LEFT_EXON_X}
          y={EXON_Y}
          width={FLANK_W}
          height={EXON_H}
          rx={3}
          fill={COLOR_FLANK}
        />
        {/* Donor warning */}
        {warnDonor && (
          <text
            x={LEFT_EXON_RIGHT + 3}
            y={EXON_Y - 3}
            fontSize={8}
            fill={COLOR_WARN}
            fontFamily="sans-serif"
          >
            ⚠ non-GT
          </text>
        )}

        {/* ── Exon flanquant droit ── */}
        <rect
          x={RIGHT_EXON_X}
          y={EXON_Y}
          width={FLANK_W}
          height={EXON_H}
          rx={3}
          fill={COLOR_FLANK}
        />
        {/* Acceptor warning */}
        {warnAcceptor && (
          <text
            x={RIGHT_EXON_LEFT - 3}
            y={EXON_Y - 3}
            textAnchor="end"
            fontSize={8}
            fill={COLOR_WARN}
            fontFamily="sans-serif"
          >
            ⚠ non-AG
          </text>
        )}

        {/* ── Intron gauche ── */}
        <IntronLine
          x1={LEFT_INTRON_START}
          x2={SKIP_X}
          y={INTRON_Y}
          size={upstreamIntronSize}
          labelAlign="center"
        />

        {/* ── Exon sauté ── */}
        <rect
          x={SKIP_X}
          y={EXON_Y}
          width={SKIP_W}
          height={EXON_H}
          rx={3}
          fill={COLOR_SKIP}
        />
        {/* Exon size inside rectangle if it fits, else below */}
        {exonSize !== null && (
          <text
            x={SKIP_X + SKIP_W / 2}
            y={EXON_Y + EXON_H / 2 + 3.5}
            textAnchor="middle"
            fontSize={9}
            fill="white"
            fontFamily="monospace"
            fontWeight="600"
          >
            {fmtSize(exonSize)} nt
          </text>
        )}

        {/* ── Intron droit ── */}
        <IntronLine
          x1={SKIP_RIGHT}
          x2={RIGHT_INTRON_END}
          y={INTRON_Y}
          size={downstreamIntronSize}
          labelAlign="center"
        />

        {/* ── Strand label ── */}
        {strand && (
          <text
            x={W - MARGIN}
            y={H - 4}
            textAnchor="end"
            fontSize={8.5}
            fill={COLOR_TEXT_MUTED}
            fontFamily="monospace"
          >
            {strand === "+" ? "5′ → 3′ (+)" : "3′ ← 5′ (−)"}
          </text>
        )}

        {/* ── "exon" labels under flanking rectangles ── */}
        <text
          x={LEFT_EXON_X + FLANK_W / 2}
          y={LABEL_Y + 2}
          textAnchor="middle"
          fontSize={8.5}
          fill={COLOR_TEXT_MUTED}
          fontFamily="sans-serif"
        >
          exon amont
        </text>
        <text
          x={RIGHT_EXON_X + FLANK_W / 2}
          y={LABEL_Y + 2}
          textAnchor="middle"
          fontSize={8.5}
          fill={COLOR_TEXT_MUTED}
          fontFamily="sans-serif"
        >
          exon aval
        </text>
      </svg>
    </div>
  );
}
