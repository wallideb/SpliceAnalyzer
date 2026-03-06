"use client";

/**
 * ConsensusLogoPanel
 * ===================
 * Publication-grade sequence logo for splice-site PWM data.
 *
 * Follows WebLogo / Schneider & Stephens (1990) standard:
 *  • Y-axis in bits of information (0 – 2)
 *  • Letter heights: height ∝ frequency × IC  (IC = 2 – H)
 *  • X-axis: numbered relative to splice site (−3…+6 for 5'SS, −20…+3 for 3'SS)
 *  • Canonical positions highlighted with yellow background
 *  • Per-column hover tooltip: position + frequency of each base in %
 *  • "Export SVG" button (downloads the raw SVG markup)
 *
 * Usage:
 *   <ConsensusLogoPanel
 *     pwm={donor_sites.pwm}
 *     title="Site donneur 5'SS"
 *     startPosition={-3}    // position number assigned to index 0
 *     skipZero               // splice-site convention: skip position 0
 *     canonicalPositions={[1, 2]}  // e.g. GT at +1,+2
 *     id="logo-donor"
 *   />
 */

import { useRef, useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PWMRow {
  A: number;
  C: number;
  G: number;
  T: number;
}

interface ConsensusLogoPanelProps {
  pwm: PWMRow[];
  title: string;
  /** Position number assigned to the first column (can be negative). */
  startPosition: number;
  /** If true, skip position 0 in the numbering (splice-site convention). */
  skipZero?: boolean;
  /**
   * 1-based position numbers (not array indices!) that should be highlighted.
   * E.g. [1, 2] for GT at +1/+2 on the donor.
   */
  canonicalPositions?: number[];
  /** Unique id for SVG export naming. */
  id?: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const BASE_COLORS: Record<string, string> = {
  A: "#22c55e",
  C: "#3b82f6",
  G: "#f97316",
  T: "#ef4444",
};

const COL_W     = 20;    // px per position column
const LOGO_H    = 60;    // max logo stack height (= 2 bits)
const BITS_AXIS_W = 28;  // left margin for bits axis
const LABEL_H   = 20;    // bottom margin for position labels
const TOP_PAD   = 4;
const SVG_H     = TOP_PAD + LOGO_H + LABEL_H;

// ---------------------------------------------------------------------------
// Entropy / IC helpers
// ---------------------------------------------------------------------------

function entropy(row: PWMRow): number {
  const bases = ["A", "C", "G", "T"] as const;
  return bases.reduce((h, b) => {
    const p = row[b];
    return h - (p > 0 ? p * Math.log2(p) : 0);
  }, 0);
}

/** Position number for column index i, skipping zero if requested. */
function posNum(i: number, start: number, skipZero: boolean): number {
  let pos = start + i;
  if (skipZero && pos >= 0) pos += 1;   // skip 0
  return pos;
}

/** Label string with sign for positive positions. */
function posLabel(pos: number): string {
  return pos > 0 ? `+${pos}` : `${pos}`;
}

// ---------------------------------------------------------------------------
// SVG export helper
// ---------------------------------------------------------------------------

function exportSVG(svgEl: SVGSVGElement, filename: string) {
  const serializer = new XMLSerializer();
  const svgStr = serializer.serializeToString(svgEl);
  const blob = new Blob([svgStr], { type: "image/svg+xml" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ConsensusLogoPanel({
  pwm,
  title,
  startPosition,
  skipZero = false,
  canonicalPositions = [],
  id = "logo",
}: ConsensusLogoPanelProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hoveredCol, setHoveredCol] = useState<number | null>(null);

  if (!pwm.length) return null;

  const canonicalSet = new Set(canonicalPositions);
  const totalCols    = pwm.length;
  const svgW         = BITS_AXIS_W + totalCols * COL_W;

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
          {title}
        </p>
        <button
          onClick={() => svgRef.current && exportSVG(svgRef.current, `${id}.svg`)}
          className="text-[9px] text-muted-foreground hover:text-foreground border border-border rounded px-1.5 py-0.5 transition-colors"
          title="Télécharger le logo en SVG"
        >
          ↓ SVG
        </button>
      </div>

      {/* Hover tooltip (frequency breakdown) */}
      {hoveredCol !== null && pwm[hoveredCol] && (() => {
        const row = pwm[hoveredCol];
        const pos = posNum(hoveredCol, startPosition, skipZero);
        const ic  = Math.max(0, 2 - entropy(row));
        return (
          <div className="flex items-center gap-3 px-2 py-1 rounded bg-popover border border-border text-[9px] font-mono">
            <span className="font-semibold text-foreground">
              {posLabel(pos)}
            </span>
            <span>IC: {ic.toFixed(2)} bits</span>
            {(["A", "C", "G", "T"] as const).map((b) => (
              <span key={b} style={{ color: BASE_COLORS[b] }}>
                {b}: {(row[b] * 100).toFixed(0)}%
              </span>
            ))}
          </div>
        );
      })()}

      <div style={{ overflowX: "auto" }}>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${svgW} ${SVG_H}`}
          style={{ width: svgW, height: SVG_H, display: "block", overflow: "visible" }}
          aria-label={title}
        >
          {/* ── Bits Y-axis ── */}
          {[0, 1, 2].map((bit) => {
            const y = TOP_PAD + LOGO_H - (bit / 2) * LOGO_H;
            return (
              <g key={bit}>
                <line
                  x1={BITS_AXIS_W - 4}
                  y1={y}
                  x2={BITS_AXIS_W}
                  y2={y}
                  stroke="#475569"
                  strokeWidth={0.8}
                />
                <text
                  x={BITS_AXIS_W - 6}
                  y={y + 3}
                  textAnchor="end"
                  fontSize={6}
                  fontFamily="monospace"
                  fill="#64748b"
                >
                  {bit}
                </text>
              </g>
            );
          })}
          {/* Y-axis line */}
          <line
            x1={BITS_AXIS_W}
            y1={TOP_PAD}
            x2={BITS_AXIS_W}
            y2={TOP_PAD + LOGO_H}
            stroke="#475569"
            strokeWidth={0.8}
          />
          {/* "bits" label rotated */}
          <text
            x={8}
            y={TOP_PAD + LOGO_H / 2}
            textAnchor="middle"
            fontSize={6}
            fontFamily="sans-serif"
            fill="#64748b"
            transform={`rotate(-90, 8, ${TOP_PAD + LOGO_H / 2})`}
          >
            bits
          </text>

          {/* ── Columns ── */}
          {pwm.map((row, colIdx) => {
            const ic      = Math.max(0, 2 - entropy(row));
            const colH    = (ic / 2) * LOGO_H;
            const colX    = BITS_AXIS_W + colIdx * COL_W;
            const pos     = posNum(colIdx, startPosition, skipZero);
            const isCanon = canonicalSet.has(pos);
            const isHover = hoveredCol === colIdx;

            // Sort bases ascending by frequency so the dominant one is on top
            const sorted = (["A", "C", "G", "T"] as const)
              .map((b) => ({ b, f: row[b] }))
              .sort((a, z) => a.f - z.f);

            let curY = TOP_PAD + LOGO_H;
            const letterBlocks: React.ReactNode[] = [];

            for (const { b, f } of sorted) {
              if (f <= 0) continue;
              const h = f * colH;
              curY -= h;
              letterBlocks.push(
                <rect
                  key={`${b}-bg`}
                  x={colX + 1}
                  y={curY}
                  width={COL_W - 2}
                  height={h}
                  fill={BASE_COLORS[b]}
                  opacity={0.85}
                />,
              );
              if (h >= 9) {
                letterBlocks.push(
                  <text
                    key={`${b}-txt`}
                    x={colX + COL_W / 2}
                    y={curY + h - 2}
                    textAnchor="middle"
                    fontSize={Math.min(h - 1, COL_W - 3)}
                    fontFamily="monospace"
                    fontWeight="700"
                    fill="white"
                  >
                    {b}
                  </text>,
                );
              }
            }

            return (
              <g
                key={colIdx}
                onMouseEnter={() => setHoveredCol(colIdx)}
                onMouseLeave={() => setHoveredCol(null)}
                style={{ cursor: "crosshair" }}
              >
                {/* Highlight band for canonical positions */}
                {isCanon && (
                  <rect
                    x={colX}
                    y={TOP_PAD}
                    width={COL_W}
                    height={LOGO_H}
                    fill="#fef08a"
                    opacity={0.3}
                  />
                )}
                {/* Hover band */}
                {isHover && (
                  <rect
                    x={colX}
                    y={TOP_PAD}
                    width={COL_W}
                    height={LOGO_H}
                    fill="#e2e8f0"
                    opacity={0.35}
                  />
                )}
                {letterBlocks}
                {/* Position label */}
                <text
                  x={colX + COL_W / 2}
                  y={TOP_PAD + LOGO_H + LABEL_H - 4}
                  textAnchor="middle"
                  fontSize={isCanon ? 7 : 6}
                  fontFamily="monospace"
                  fontWeight={isCanon ? "700" : "400"}
                  fill={isCanon ? "#b45309" : "#94a3b8"}
                >
                  {posLabel(pos)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
