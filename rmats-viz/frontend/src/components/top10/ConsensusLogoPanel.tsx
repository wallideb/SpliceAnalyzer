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
import { ScienceNote } from "@/components/ScienceNote";
import { useT } from "@/contexts/LanguageContext";

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

const COL_W     = 28;    // px per position column
const LOGO_H    = 90;    // max logo stack height (= 2 bits)
const BITS_AXIS_W = 36;  // left margin for bits axis
const LABEL_H   = 32;    // bottom margin for position labels + axis title
const TOP_PAD   = 6;
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

function exportSVG(svgEl: SVGSVGElement, filename: string, title: string) {
  // Clone the SVG and make it self-contained with white background + title
  const clone = svgEl.cloneNode(true) as SVGSVGElement;
  const vb = clone.getAttribute("viewBox")?.split(" ").map(Number) ?? [0, 0, 300, 100];
  const [vx, vy, vw, vh] = vb;

  // Add padding for title at top
  const PAD_TOP = 18;
  const PAD_BOTTOM = 14;
  const newH = vh + PAD_TOP + PAD_BOTTOM;
  clone.setAttribute("viewBox", `${vx} ${vy - PAD_TOP} ${vw} ${newH}`);
  clone.setAttribute("width", String(vw * 2));
  clone.setAttribute("height", String(newH * 2));
  clone.removeAttribute("style");

  // White background
  const bg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  bg.setAttribute("x", String(vx));
  bg.setAttribute("y", String(vy - PAD_TOP));
  bg.setAttribute("width", String(vw));
  bg.setAttribute("height", String(newH));
  bg.setAttribute("fill", "white");
  clone.insertBefore(bg, clone.firstChild);

  // Title text
  const titleEl = document.createElementNS("http://www.w3.org/2000/svg", "text");
  titleEl.setAttribute("x", String(vx + vw / 2));
  titleEl.setAttribute("y", String(vy - 4));
  titleEl.setAttribute("text-anchor", "middle");
  titleEl.setAttribute("font-size", "9");
  titleEl.setAttribute("font-family", "Helvetica, Arial, sans-serif");
  titleEl.setAttribute("font-weight", "bold");
  titleEl.setAttribute("fill", "#1e293b");
  titleEl.textContent = title;
  clone.appendChild(titleEl);

  // X-axis title
  const xLabel = document.createElementNS("http://www.w3.org/2000/svg", "text");
  xLabel.setAttribute("x", String(vx + vw / 2));
  xLabel.setAttribute("y", String(vy + vh + PAD_BOTTOM - 2));
  xLabel.setAttribute("text-anchor", "middle");
  xLabel.setAttribute("font-size", "7");
  xLabel.setAttribute("font-family", "Helvetica, Arial, sans-serif");
  xLabel.setAttribute("font-style", "italic");
  xLabel.setAttribute("fill", "#64748b");
  xLabel.textContent = "Position relative to splice site";
  clone.appendChild(xLabel);

  const serializer = new XMLSerializer();
  const svgStr = '<?xml version="1.0" encoding="UTF-8"?>\n' + serializer.serializeToString(clone);
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
  const t = useT();
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
          onClick={() => svgRef.current && exportSVG(svgRef.current, `${id}.svg`, title)}
          className="text-[9px] text-muted-foreground hover:text-foreground border border-border rounded px-1.5 py-0.5 transition-colors"
          title={t("eventTable.downloadSvg")}
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
          {/* ── Bits Y-axis with grid lines ── */}
          {[0, 0.5, 1, 1.5, 2].map((bit) => {
            const y = TOP_PAD + LOGO_H - (bit / 2) * LOGO_H;
            const isMajor = bit % 1 === 0;
            return (
              <g key={bit}>
                {/* Grid line across chart area */}
                <line
                  x1={BITS_AXIS_W}
                  y1={y}
                  x2={BITS_AXIS_W + totalCols * COL_W}
                  y2={y}
                  stroke="#e2e8f0"
                  strokeWidth={isMajor ? 0.5 : 0.3}
                  strokeDasharray={isMajor ? undefined : "2 2"}
                />
                {/* Tick mark */}
                <line
                  x1={BITS_AXIS_W - (isMajor ? 4 : 2)}
                  y1={y}
                  x2={BITS_AXIS_W}
                  y2={y}
                  stroke="#475569"
                  strokeWidth={0.8}
                />
                {/* Label (only for whole numbers) */}
                {isMajor && (
                  <text
                    x={BITS_AXIS_W - 6}
                    y={y + 3}
                    textAnchor="end"
                    fontSize={7}
                    fontFamily="monospace"
                    fill="#64748b"
                  >
                    {bit}
                  </text>
                )}
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
          {/* Y-axis label rotated */}
          <text
            x={8}
            y={TOP_PAD + LOGO_H / 2}
            textAnchor="middle"
            fontSize={7}
            fontFamily="sans-serif"
            fontStyle="italic"
            fill="#64748b"
            transform={`rotate(-90, 8, ${TOP_PAD + LOGO_H / 2})`}
          >
            Information (bits)
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
                  y={TOP_PAD + LOGO_H + 14}
                  textAnchor="middle"
                  fontSize={isCanon ? 8 : 7}
                  fontFamily="monospace"
                  fontWeight={isCanon ? "700" : "400"}
                  fill={isCanon ? "#b45309" : "#94a3b8"}
                >
                  {posLabel(pos)}
                </text>
              </g>
            );
          })}

          {/* X-axis title */}
          <text
            x={BITS_AXIS_W + (totalCols * COL_W) / 2}
            y={SVG_H - 2}
            textAnchor="middle"
            fontSize={7}
            fontFamily="sans-serif"
            fontStyle="italic"
            fill="#64748b"
          >
            Position relative to splice site
          </text>
        </svg>
      </div>
      <ScienceNote
        title={t("scienceNotes.consensusLogo.title")}
        body={t("scienceNotes.consensusLogo.body")}
        refs={["sequence_logos", "shannon", "splice_sites"]}
      />
    </div>
  );
}
