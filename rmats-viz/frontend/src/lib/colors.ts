/**
 * Nucleotide colour palette — single source of truth (E7).
 * =========================================================
 * Used by ExonDiagram, SpliceSiteTrack, ConsensusLogoPanel and PPTTrack so
 * that A/C/G/T are drawn with the same colours everywhere in the UI.
 */

export const BASE_COLORS = {
  A: "#22c55e", // green-500
  C: "#3b82f6", // blue-500
  G: "#f97316", // orange-500
  T: "#ef4444", // red-500
  N: "#94a3b8", // slate-400 (unknown / ambiguous)
} as const;

export type Base = keyof typeof BASE_COLORS;

/**
 * Colour for a single nucleotide letter. IUPAC ambiguity codes fall back to
 * the colour of the "representative" base (Y → C, R → A, U → T), everything
 * else to N (grey).
 */
export function baseColor(base: string): string {
  const b = base.toUpperCase();
  if (b in BASE_COLORS) return BASE_COLORS[b as Base];
  if (b === "U") return BASE_COLORS.T;
  if (b === "Y") return BASE_COLORS.C; // pyrimidine
  if (b === "R") return BASE_COLORS.A; // purine
  return BASE_COLORS.N;
}
