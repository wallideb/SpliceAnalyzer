"use client";

import { posNum, posLabel } from "@/lib/utils";

/**
 * SpliceSequenceLogo
 * ==================
 * Minimal sequence logo rendered as inline SVG.
 *
 * Each position is drawn as a stack of letters whose height is proportional
 * to their frequency in the PWM (position weight matrix).  The total column
 * height is scaled by information content (IC = 2 – entropy) so highly
 * conserved positions are tall and degenerate ones are short.
 *
 * Canonical base colours: A=green, C=blue, G=orange, T=red.
 */

const BASE_COLORS: Record<string, string> = {
  A: "#22c55e",   // green-500
  C: "#3b82f6",   // blue-500
  G: "#f97316",   // orange-500
  T: "#ef4444",   // red-500
};

interface PWMRow {
  A: number;
  C: number;
  G: number;
  T: number;
}

interface SpliceSequenceLogoProps {
  pwm: PWMRow[];
  /** Optional: highlight these 0-based positions with a yellow tint column */
  highlight?: number[];
  /** Column width in px */
  colWidth?: number;
  /** Max logo height in px */
  maxHeight?: number;
  /** Position number assigned to the first column (e.g. -3 for donor, -20 for acceptor). Default 1. */
  startPosition?: number;
  /** If true, skip position 0 in the numbering (splice-site convention). Default false. */
  skipZero?: boolean;
}

function entropy(row: PWMRow): number {
  const bases: (keyof PWMRow)[] = ["A", "C", "G", "T"];
  return bases.reduce((h, b) => {
    const p = row[b];
    return h - (p > 0 ? p * Math.log2(p) : 0);
  }, 0);
}

export function SpliceSequenceLogo({
  pwm,
  highlight = [],
  colWidth = 18,
  maxHeight = 48,
  startPosition = 1,
  skipZero = false,
}: SpliceSequenceLogoProps) {
  if (!pwm.length) return null;

  const highlightSet = new Set(highlight);
  const W = pwm.length * colWidth;
  const H = maxHeight + 14; // extra for position labels

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width={W}
      height={H}
      className="overflow-visible"
      aria-label="Sequence logo"
    >
      {pwm.map((row, posIdx) => {
        const ic = Math.max(0, 2 - entropy(row)); // bits, 0–2
        const colH = (ic / 2) * maxHeight;
        const x = posIdx * colWidth;
        const isHL = highlightSet.has(posIdx);

        // Sort bases by frequency (ascending) so highest is on top
        const sorted = (["A", "C", "G", "T"] as const)
          .map((b) => ({ b, f: row[b] }))
          .sort((a, z) => a.f - z.f);

        let curY = maxHeight; // draw upward from bottom
        const rects: React.ReactNode[] = [];

        for (const { b, f } of sorted) {
          if (f <= 0) continue;
          const h = f * colH;
          curY -= h;
          rects.push(
            <rect
              key={b}
              x={x + 1}
              y={curY}
              width={colWidth - 2}
              height={h}
              fill={BASE_COLORS[b]}
              opacity={0.85}
            />
          );
          // Letter label if tall enough
          if (h >= 10) {
            rects.push(
              <text
                key={`${b}-txt`}
                x={x + colWidth / 2}
                y={curY + h - 2}
                textAnchor="middle"
                fontSize={Math.min(h - 1, colWidth - 2)}
                fontFamily="monospace"
                fontWeight="700"
                fill="white"
              >
                {b}
              </text>
            );
          }
        }

        return (
          <g key={posIdx}>
            {/* Highlight background */}
            {isHL && (
              <rect
                x={x}
                y={0}
                width={colWidth}
                height={maxHeight}
                fill="var(--svg-highlight-bg)"
                opacity={0.4}
              />
            )}
            {rects}
            {/* Position label */}
            <text
              x={x + colWidth / 2}
              y={maxHeight + 11}
              textAnchor="middle"
              fontSize={8}
              fill="#94a3b8"
              fontFamily="monospace"
            >
              {posLabel(posNum(posIdx, startPosition, skipZero))}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
