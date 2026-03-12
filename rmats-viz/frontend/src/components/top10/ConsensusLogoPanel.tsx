"use client";

/**
 * ConsensusLogoPanel
 * ===================
 * Publication-grade sequence logo for splice-site PWM data.
 *
 * Follows WebLogo3 / Schneider & Stephens (1990) standard:
 *  • Y-axis in bits of information (0 – 2)
 *  • Letter heights: height = frequency × R_i  where R_i = 2 − H_i − e_n
 *  • Small-sample correction: e_n = (s−1) / (2 · ln2 · n)  (Schneider et al. 1986)
 *  • Letters rendered as vertically-stretched glyphs (not colored rectangles)
 *  • X-axis: numbered relative to splice site
 *  • Canonical positions highlighted with yellow background
 *
 * References:
 *  Schneider TD, Stephens RM. 1990. Nucleic Acids Res. 18:6097-6100
 *  Crooks GE et al. 2004. Genome Research 14:1188-1190
 */

import { useRef, useState } from "react";
import { ScienceNote } from "@/components/ScienceNote";
import { useT } from "@/contexts/LanguageContext";
import { posNum, posLabel } from "@/lib/utils";

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
  startPosition: number;
  skipZero?: boolean;
  canonicalPositions?: number[];
  id?: string;
  /** Number of sequences used to compute the PWM (for small-sample correction). */
  nSequences?: number;
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

const COL_W     = 28;
const LOGO_H    = 90;
const BITS_AXIS_W = 36;
const LABEL_H   = 32;
const TOP_PAD   = 6;
const SVG_H     = TOP_PAD + LOGO_H + LABEL_H;

// ---------------------------------------------------------------------------
// Entropy / IC helpers (Schneider & Stephens 1990, Schneider et al. 1986)
// ---------------------------------------------------------------------------

function entropy(row: PWMRow): number {
  const bases = ["A", "C", "G", "T"] as const;
  return bases.reduce((h, b) => {
    const p = row[b];
    return h - (p > 0 ? p * Math.log2(p) : 0);
  }, 0);
}

/** Small-sample correction: e_n = (s-1) / (2·ln(2)·n) for s=4 (DNA). */
function smallSampleCorrection(n: number | undefined): number {
  if (!n || n <= 0) return 0;
  return 3 / (2 * Math.LN2 * n);
}

// ---------------------------------------------------------------------------
// SVG export helper
// ---------------------------------------------------------------------------

function exportSVG(svgEl: SVGSVGElement, filename: string, title: string) {
  const clone = svgEl.cloneNode(true) as SVGSVGElement;
  const vb = clone.getAttribute("viewBox")?.split(" ").map(Number) ?? [0, 0, 300, 100];
  const [vx, vy, vw, vh] = vb;

  const PAD_TOP = 18;
  const PAD_BOTTOM = 14;
  const newH = vh + PAD_TOP + PAD_BOTTOM;
  clone.setAttribute("viewBox", `${vx} ${vy - PAD_TOP} ${vw} ${newH}`);
  clone.setAttribute("width", String(vw * 2));
  clone.setAttribute("height", String(newH * 2));
  clone.removeAttribute("style");

  const bg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  bg.setAttribute("x", String(vx));
  bg.setAttribute("y", String(vy - PAD_TOP));
  bg.setAttribute("width", String(vw));
  bg.setAttribute("height", String(newH));
  bg.setAttribute("fill", "white");
  clone.insertBefore(bg, clone.firstChild);

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
  nSequences,
}: ConsensusLogoPanelProps) {
  const t = useT();
  const svgRef = useRef<SVGSVGElement>(null);
  const [hoveredCol, setHoveredCol] = useState<number | null>(null);

  if (!pwm.length) return null;

  const en = smallSampleCorrection(nSequences);
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
        const ic  = Math.max(0, 2 - entropy(row) - en);
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
                <line
                  x1={BITS_AXIS_W}
                  y1={y}
                  x2={BITS_AXIS_W + totalCols * COL_W}
                  y2={y}
                  stroke="#e2e8f0"
                  strokeWidth={isMajor ? 0.5 : 0.3}
                  strokeDasharray={isMajor ? undefined : "2 2"}
                />
                <line
                  x1={BITS_AXIS_W - (isMajor ? 4 : 2)}
                  y1={y}
                  x2={BITS_AXIS_W}
                  y2={y}
                  stroke="#475569"
                  strokeWidth={0.8}
                />
                {isMajor && (
                  <text
                    x={BITS_AXIS_W - 6}
                    y={y + 3}
                    textAnchor="end"
                    fontSize={7}
                    fontFamily="monospace"
                    fill="hsl(var(--muted-foreground))"
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
            fill="hsl(var(--muted-foreground))"
            transform={`rotate(-90, 8, ${TOP_PAD + LOGO_H / 2})`}
          >
            Information (bits)
          </text>

          {/* ── Columns ── */}
          {pwm.map((row, colIdx) => {
            const ic      = Math.max(0, 2 - entropy(row) - en);
            const colH    = (ic / 2) * LOGO_H;
            const colX    = BITS_AXIS_W + colIdx * COL_W;
            const pos     = posNum(colIdx, startPosition, skipZero);
            const isCanon = canonicalSet.has(pos);
            const isHover = hoveredCol === colIdx;

            // Sort bases ascending by frequency so the dominant one is on top
            const sorted = (["A", "C", "G", "T"] as const)
              .map((b) => ({ b, f: row[b] }))
              .sort((a, z) => a.f - z.f);

            // When IC ≈ 0 after correction, show faint frequency-based letters
            // so every position with data shows something (minimum 3px column).
            const rawIc   = Math.max(0, 2 - entropy(row));
            const MIN_COL = 3;
            const showFaint = ic < 0.05 && rawIc > 0;
            const effectiveColH = showFaint ? MIN_COL : colH;

            let curY = TOP_PAD + LOGO_H;
            const letterGlyphs: React.ReactNode[] = [];

            // Reference glyph metrics: at fontSize = COL_W, cap-height ≈ 0.72 × fontSize
            const REF_FS = COL_W;
            const CAP_H = REF_FS * 0.72;

            for (const { b, f } of sorted) {
              if (f <= 0) continue;
              const h = f * effectiveColH;
              if (h < 0.15) { curY -= h; continue; }
              curY -= h;

              // Scale the letter glyph so it fills exactly width=COL_W-2, height=h
              const sx = (COL_W - 2) / REF_FS;
              const sy = h / CAP_H;
              // Place baseline at bottom of allocated band, then scale from that point
              const bx = colX + COL_W / 2;
              const by = curY + h;

              letterGlyphs.push(
                <g key={b} transform={`translate(${bx},${by}) scale(${sx},${sy})`}>
                  <text
                    x={0}
                    y={0}
                    textAnchor="middle"
                    dominantBaseline="alphabetic"
                    fontSize={REF_FS}
                    fontFamily="Arial Black, Impact, Helvetica, sans-serif"
                    fontWeight="900"
                    fill={BASE_COLORS[b]}
                    opacity={showFaint ? 0.25 : 1}
                  >
                    {b}
                  </text>
                </g>,
              );
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
                    fill="var(--svg-highlight-bg)"
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
                    fill="hsl(var(--muted))"
                    opacity={0.35}
                  />
                )}
                {letterGlyphs}
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
            fill="hsl(var(--muted-foreground))"
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
