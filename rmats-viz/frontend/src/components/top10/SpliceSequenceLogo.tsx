"use client";

import { posNum, posLabel } from "@/lib/utils";

/**
 * SpliceSequenceLogo
 * ==================
 * Minimal sequence logo rendered as inline SVG using WebLogo3-standard
 * stretched letter glyphs.
 *
 * Each position is drawn as a stack of letters whose height is proportional
 * to their frequency × information content (IC = 2 − H − e_n).
 *
 * Canonical base colours: A=green, C=blue, G=orange, T=red.
 */

const BASE_COLORS: Record<string, string> = {
  A: "#22c55e",
  C: "#3b82f6",
  G: "#f97316",
  T: "#ef4444",
};

interface PWMRow {
  A: number;
  C: number;
  G: number;
  T: number;
}

interface SpliceSequenceLogoProps {
  pwm: PWMRow[];
  highlight?: number[];
  colWidth?: number;
  maxHeight?: number;
  startPosition?: number;
  skipZero?: boolean;
  nSequences?: number;
}

function entropy(row: PWMRow): number {
  const bases: (keyof PWMRow)[] = ["A", "C", "G", "T"];
  return bases.reduce((h, b) => {
    const p = row[b];
    return h - (p > 0 ? p * Math.log2(p) : 0);
  }, 0);
}

function smallSampleCorrection(n: number | undefined): number {
  if (!n || n <= 0) return 0;
  return 3 / (2 * Math.LN2 * n);
}

export function SpliceSequenceLogo({
  pwm,
  highlight = [],
  colWidth = 18,
  maxHeight = 48,
  startPosition = 1,
  skipZero = false,
  nSequences,
}: SpliceSequenceLogoProps) {
  if (!pwm.length) return null;

  const en = smallSampleCorrection(nSequences);
  const highlightSet = new Set(highlight);
  const W = pwm.length * colWidth;
  const H = maxHeight + 14;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width={W}
      height={H}
      className="overflow-visible"
      aria-label="Sequence logo"
    >
      {pwm.map((row, posIdx) => {
        const ic = Math.max(0, 2 - entropy(row) - en);
        const colH = (ic / 2) * maxHeight;
        const x = posIdx * colWidth;
        const isHL = highlightSet.has(posIdx);

        const sorted = (["A", "C", "G", "T"] as const)
          .map((b) => ({ b, f: row[b] }))
          .sort((a, z) => a.f - z.f);

        let curY = maxHeight;
        const glyphs: React.ReactNode[] = [];

        for (const { b, f } of sorted) {
          if (f <= 0) continue;
          const h = f * colH;
          if (h < 0.5) { curY -= h; continue; }
          curY -= h;

          glyphs.push(
            <svg
              key={b}
              x={x + 1}
              y={curY}
              width={colWidth - 2}
              height={h}
              viewBox="0 0 100 100"
              preserveAspectRatio="none"
            >
              <text
                x="50"
                y="95"
                textAnchor="middle"
                fontSize="110"
                fontFamily="Arial Black, Impact, Helvetica, sans-serif"
                fontWeight="900"
                fill={BASE_COLORS[b]}
              >
                {b}
              </text>
            </svg>,
          );
        }

        return (
          <g key={posIdx}>
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
            {glyphs}
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
