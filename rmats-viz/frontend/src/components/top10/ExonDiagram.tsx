"use client";

/**
 * ExonDiagram — Publication-style SVG exon-skipping diagram (full-width)
 * ========================================================================
 * viewBox 0 0 900 180 — chaque zone est interactive (title tooltip natif SVG).
 *
 * Tooltips disponibles :
 *  - Arc           → FDR, ΔΨ, p-value, PSI groupe 1 & 2
 *  - Exon sauté    → coordonnées, taille, frame class, MANE, rang exon
 *  - Exons flanc.  → coordonnées
 *  - Zone Donor    → séquence 9 nt avec GT balisé
 *  - Zone Acceptor → séquence 23 nt avec AG balisé
 *  - Barre PPT     → score + interprétation
 *  - Point BP      → trouvé/non trouvé, distance
 *  - Badge Frame   → class, transcrit MANE, rang exon
 */

import React from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ExonDiagramProps {
  exonSize: number | null;
  upstreamIntronSize: number | null;
  downstreamIntronSize: number | null;
  incLevelDifference: number | null;
  fdr: number | null;
  pValue: number | null;
  strand: string | null;
  donorIsGt?: boolean | null;
  acceptorIsAg?: boolean | null;
  // Extended — tooltips
  psi1?: number | null;
  psi2?: number | null;
  exonStart?: number | null;
  exonEnd?: number | null;
  upstreamExonStart?: number | null;
  upstreamExonEnd?: number | null;
  downstreamExonStart?: number | null;
  downstreamExonEnd?: number | null;
  frameClass?: string | null;
  maneTranscriptId?: string | null;
  exonRank?: number | null;
  donorSeq?: string | null;
  acceptorSeq?: string | null;
  pptScore?: number | null;
  pptSeq?: string | null;
  bpFound?: boolean | null;
  bpDistance?: number | null;
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

function fmtCoord(v: number | null): string {
  if (v === null) return "?";
  return v.toLocaleString();
}

// ---------------------------------------------------------------------------
// Layout constants (SVG user units, viewBox 900×180)
// ---------------------------------------------------------------------------

const W = 900;
const H = 180;

const EXON_Y   = 78;
const EXON_H   = 32;
const INTRON_Y = EXON_Y + EXON_H / 2;
const LABEL_Y  = EXON_Y + EXON_H + 16;

const FLANK_W  = 90;
const SKIP_W   = 160;
const MARGIN   = 30;

const LEFT_EXON_X    = MARGIN;
const LEFT_EXON_RIGHT = LEFT_EXON_X + FLANK_W;   // 120
const RIGHT_EXON_X   = W - MARGIN - FLANK_W;      // 780
const RIGHT_EXON_LEFT = RIGHT_EXON_X;             // 780

const SKIP_X     = (W - SKIP_W) / 2;  // 370
const SKIP_RIGHT = SKIP_X + SKIP_W;   // 530

const ARC_TOP_Y = 14;

// Site donor / acceptor indicator zones
const SITE_W = 20;
const SITE_H = EXON_H + 10;

// PPT bar (bottom area)
const PPT_Y      = 152;
const PPT_H      = 8;
const PPT_BAR_X1 = 560;
const PPT_BAR_X2 = RIGHT_EXON_LEFT; // 780
const BP_CY      = PPT_Y + PPT_H / 2;

// Colours
const COLOR_FLANK      = "#94a3b8";
const COLOR_SKIP       = "#6366f1";
const COLOR_BLUE       = "#3b82f6";
const COLOR_RED        = "#ef4444";
const COLOR_WARN       = "#f59e0b";
const COLOR_GREEN      = "#22c55e";
const COLOR_AMBER      = "#f59e0b";
const COLOR_TEXT_MUTED = "#94a3b8";

// Frame badge colours
const FRAME_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  in_frame:   { bg: "#14532d", text: "#86efac", border: "#15803d" },
  frameshift: { bg: "#7f1d1d", text: "#fca5a5", border: "#b91c1c" },
  non_coding: { bg: "#1e293b", text: "#94a3b8", border: "#334155" },
  partial:    { bg: "#7c2d12", text: "#fdba74", border: "#c2410c" },
  unknown:    { bg: "#1e293b", text: "#64748b", border: "#334155" },
};
const FRAME_LABELS: Record<string, string> = {
  in_frame:   "In-frame",
  frameshift: "Frameshift",
  non_coding: "Non-coding",
  partial:    "Partial",
  unknown:    "?",
};

// ---------------------------------------------------------------------------
// IntronLine sub-component
// ---------------------------------------------------------------------------

function IntronLine({
  x1, x2, y, size,
}: {
  x1: number; x2: number; y: number; size: number | null;
}) {
  const mid = (x1 + x2) / 2;
  const notchDepth = 9;
  const d = `M ${x1} ${y} L ${mid} ${y + notchDepth} L ${x2} ${y}`;
  return (
    <g>
      <path d={d} stroke={COLOR_FLANK} strokeWidth={1.5} fill="none" />
      {size !== null && (
        <text
          x={mid} y={LABEL_Y + 2}
          textAnchor="middle" fontSize={10}
          fill={COLOR_TEXT_MUTED} fontFamily="monospace"
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
  psi1,
  psi2,
  exonStart,
  exonEnd,
  upstreamExonStart,
  upstreamExonEnd,
  downstreamExonStart,
  downstreamExonEnd,
  frameClass,
  maneTranscriptId,
  exonRank,
  donorSeq,
  acceptorSeq,
  pptScore,
  pptSeq,
  bpFound,
  bpDistance,
}: ExonDiagramProps) {

  const delta    = incLevelDifference ?? 0;
  const arcColor = delta < 0 ? COLOR_BLUE : COLOR_RED;
  const arcWidth = Math.max(2, Math.min(6, 2 + Math.abs(delta) * 6));
  const arcDashed = fdr !== null && fdr > 0.05;

  // Arc path
  const arcStartX = LEFT_EXON_RIGHT;
  const arcStartY = EXON_Y;
  const arcEndX   = RIGHT_EXON_LEFT;
  const arcEndY   = EXON_Y;
  const arcMidX   = W / 2;
  const cp1x = arcStartX + (arcMidX - arcStartX) * 0.4;
  const cp2x = arcMidX   + (arcEndX  - arcMidX)  * 0.6;
  const arcPath = `M ${arcStartX} ${arcStartY} C ${cp1x} ${ARC_TOP_Y}, ${cp2x} ${ARC_TOP_Y}, ${arcEndX} ${arcEndY}`;

  // ── Tooltips ──────────────────────────────────────────────────────────────

  const arcTooltip = [
    fdr !== null              ? `FDR: ${fmtPval(fdr)}`                               : null,
    incLevelDifference !== null ? `ΔΨ: ${fmtDelta(incLevelDifference)}`              : null,
    pValue !== null           ? `p-value: ${fmtPval(pValue)}`                        : null,
    psi1 != null              ? `PSI groupe 1 (moy.): ${psi1.toFixed(3)}`            : null,
    psi2 != null              ? `PSI groupe 2 (moy.): ${psi2.toFixed(3)}`            : null,
  ].filter(Boolean).join("\n");

  const skipTooltip = [
    exonSize !== null         ? `Taille: ${fmtSize(exonSize)} nt`                    : null,
    exonStart != null && exonEnd != null
      ? `Coordonnées: ${fmtCoord(exonStart)}–${fmtCoord(exonEnd)}`                  : null,
    frameClass                ? `Frame: ${FRAME_LABELS[frameClass] ?? frameClass}`   : null,
    maneTranscriptId          ? `MANE: ${maneTranscriptId}`                          : null,
    exonRank != null          ? `Rang exon: ${exonRank}`                             : null,
  ].filter(Boolean).join("\n");

  const upstreamTooltip = [
    "Exon flanquant amont",
    upstreamExonStart != null && upstreamExonEnd != null
      ? `Coordonnées: ${fmtCoord(upstreamExonStart)}–${fmtCoord(upstreamExonEnd)}`  : null,
  ].filter(Boolean).join("\n");

  const downstreamTooltip = [
    "Exon flanquant aval",
    downstreamExonStart != null && downstreamExonEnd != null
      ? `Coordonnées: ${fmtCoord(downstreamExonStart)}–${fmtCoord(downstreamExonEnd)}` : null,
  ].filter(Boolean).join("\n");

  const donorTooltip = donorSeq
    ? [
        `Site donneur 5'SS (${donorIsGt === false ? "⚠ non-GT" : "GT canonique"})`,
        `Séquence 9 nt: ${donorSeq.slice(0, 3)}[${donorSeq.slice(3, 5)}]${donorSeq.slice(5)}`,
      ].join("\n")
    : `Site donneur 5'SS${donorIsGt === false ? " ⚠ non-GT" : ""}`;

  const acceptorTooltip = acceptorSeq
    ? [
        `Site accepteur 3'SS (${acceptorIsAg === false ? "⚠ non-AG" : "AG canonique"})`,
        `Séquence 23 nt: ${acceptorSeq.slice(0, 17)}[${acceptorSeq.slice(17, 19)}]${acceptorSeq.slice(19)}`,
      ].join("\n")
    : `Site accepteur 3'SS${acceptorIsAg === false ? " ⚠ non-AG" : ""}`;

  const pptInterpret =
    (pptScore ?? 0) >= 0.7 ? "PPT fort" :
    (pptScore ?? 0) >= 0.5 ? "PPT modéré" : "PPT faible";
  const pptTooltip = [
    "Zone polypyrimidine (PPT — 47 nt avant 3'SS)",
    pptScore != null ? `Score Y: ${Math.round((pptScore) * 100)}% — ${pptInterpret}` : null,
    pptSeq   ? `Séquence: ${pptSeq.slice(0, 24)}…` : null,
  ].filter(Boolean).join("\n");

  const bpTooltip = bpFound
    ? `Point de branchement (YNYURAY)\nTrouvé — distance ~${bpDistance} nt du 3'SS`
    : "Point de branchement (YNYURAY)\nNon détecté dans la région PPT";

  const fc           = frameClass ?? "unknown";
  const frameColors  = FRAME_COLORS[fc] ?? FRAME_COLORS.unknown;
  const frameLabel   = FRAME_LABELS[fc] ?? fc;
  const frameBadgeTooltip = [
    `Frame: ${frameLabel}`,
    maneTranscriptId ? `Transcrit MANE: ${maneTranscriptId}` : "MANE: non trouvé",
    exonRank != null ? `Rang exon: ${exonRank}` : null,
  ].filter(Boolean).join("\n");

  const warnDonor    = donorIsGt    === false;
  const warnAcceptor = acceptorIsAg === false;

  // PPT bar width
  const pptBarFill = pptScore != null
    ? (PPT_BAR_X2 - PPT_BAR_X1) * Math.min(1, Math.max(0, pptScore))
    : 0;

  return (
    <div className="w-full">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: "100%", display: "block" }}
        aria-label="Diagramme exon sauté"
        role="img"
      >
        {/* ── Arc de saut ── */}
        <g style={{ cursor: "help" }}>
          {/* hit area transparent plus large */}
          <path d={arcPath} stroke="transparent" strokeWidth={18} fill="none" />
          <path
            d={arcPath}
            stroke={arcColor}
            strokeWidth={arcWidth}
            fill="none"
            strokeDasharray={arcDashed ? "6 3" : undefined}
            strokeLinecap="round"
          />
          <title>{arcTooltip}</title>
        </g>

        {/* Stats inline au-dessus de l'arc */}
        {(fdr !== null || incLevelDifference !== null) && (
          <text
            x={arcMidX} y={ARC_TOP_Y - 1}
            textAnchor="middle" fontSize={9.5}
            fill={arcColor} fontFamily="monospace" fontWeight="600"
          >
            {[
              fdr !== null              ? `FDR ${fmtPval(fdr)}`          : null,
              incLevelDifference !== null ? `ΔΨ ${fmtDelta(incLevelDifference)}` : null,
            ].filter(Boolean).join("  |  ")}
          </text>
        )}

        {/* ── Exon flanquant gauche ── */}
        <g style={{ cursor: "help" }}>
          <rect x={LEFT_EXON_X} y={EXON_Y} width={FLANK_W} height={EXON_H} rx={4} fill={COLOR_FLANK} />
          <title>{upstreamTooltip}</title>
        </g>
        <text
          x={LEFT_EXON_X + FLANK_W / 2} y={LABEL_Y + 2}
          textAnchor="middle" fontSize={9}
          fill={COLOR_TEXT_MUTED} fontFamily="sans-serif"
        >
          exon amont
        </text>

        {/* ── Zone Donor (5'SS) ── */}
        <g style={{ cursor: "help" }}>
          <rect
            x={LEFT_EXON_RIGHT - 5}
            y={EXON_Y - 4}
            width={SITE_W}
            height={SITE_H}
            rx={2}
            fill={warnDonor ? COLOR_WARN : COLOR_GREEN}
            fillOpacity={0.22}
            stroke={warnDonor ? COLOR_WARN : COLOR_GREEN}
            strokeWidth={1}
          />
          <title>{donorTooltip}</title>
        </g>
        {warnDonor && (
          <text x={LEFT_EXON_RIGHT + 2} y={EXON_Y - 7} fontSize={8} fill={COLOR_WARN} fontFamily="sans-serif">
            ⚠ non-GT
          </text>
        )}

        {/* ── Intron gauche ── */}
        <IntronLine x1={LEFT_EXON_RIGHT} x2={SKIP_X} y={INTRON_Y} size={upstreamIntronSize} />

        {/* ── Exon sauté ── */}
        <g style={{ cursor: "help" }}>
          <rect x={SKIP_X} y={EXON_Y} width={SKIP_W} height={EXON_H} rx={4} fill={COLOR_SKIP} />
          {exonSize !== null && (
            <text
              x={SKIP_X + SKIP_W / 2} y={EXON_Y + EXON_H / 2 + 4}
              textAnchor="middle" fontSize={11}
              fill="white" fontFamily="monospace" fontWeight="700"
            >
              {fmtSize(exonSize)} nt
            </text>
          )}
          <title>{skipTooltip}</title>
        </g>

        {/* Frame badge sous l'exon sauté */}
        {frameClass && frameClass !== "unknown" && (
          <g style={{ cursor: "help" }}>
            <rect
              x={SKIP_X + SKIP_W / 2 - 36}
              y={EXON_Y + EXON_H + 5}
              width={72}
              height={15}
              rx={3}
              fill={frameColors.bg}
              stroke={frameColors.border}
              strokeWidth={0.8}
            />
            <text
              x={SKIP_X + SKIP_W / 2}
              y={EXON_Y + EXON_H + 15}
              textAnchor="middle" fontSize={8.5}
              fill={frameColors.text} fontFamily="monospace" fontWeight="600"
            >
              {frameLabel}
            </text>
            <title>{frameBadgeTooltip}</title>
          </g>
        )}

        {/* ── Intron droit ── */}
        <IntronLine x1={SKIP_RIGHT} x2={RIGHT_EXON_LEFT} y={INTRON_Y} size={downstreamIntronSize} />

        {/* ── Zone Acceptor (3'SS) ── */}
        <g style={{ cursor: "help" }}>
          <rect
            x={RIGHT_EXON_LEFT - SITE_W + 5}
            y={EXON_Y - 4}
            width={SITE_W}
            height={SITE_H}
            rx={2}
            fill={warnAcceptor ? COLOR_WARN : COLOR_GREEN}
            fillOpacity={0.22}
            stroke={warnAcceptor ? COLOR_WARN : COLOR_GREEN}
            strokeWidth={1}
          />
          <title>{acceptorTooltip}</title>
        </g>
        {warnAcceptor && (
          <text x={RIGHT_EXON_LEFT - 2} y={EXON_Y - 7} textAnchor="end" fontSize={8} fill={COLOR_WARN} fontFamily="sans-serif">
            ⚠ non-AG
          </text>
        )}

        {/* ── Exon flanquant droit ── */}
        <g style={{ cursor: "help" }}>
          <rect x={RIGHT_EXON_X} y={EXON_Y} width={FLANK_W} height={EXON_H} rx={4} fill={COLOR_FLANK} />
          <title>{downstreamTooltip}</title>
        </g>
        <text
          x={RIGHT_EXON_X + FLANK_W / 2} y={LABEL_Y + 2}
          textAnchor="middle" fontSize={9}
          fill={COLOR_TEXT_MUTED} fontFamily="sans-serif"
        >
          exon aval
        </text>

        {/* ── Barre PPT ── */}
        {pptScore != null && (
          <g style={{ cursor: "help" }}>
            <text
              x={PPT_BAR_X1 - 5} y={PPT_Y + PPT_H - 1}
              textAnchor="end" fontSize={8}
              fill={COLOR_TEXT_MUTED} fontFamily="monospace"
            >
              PPT {Math.round(pptScore * 100)}%
            </text>
            {/* fond */}
            <rect
              x={PPT_BAR_X1} y={PPT_Y}
              width={PPT_BAR_X2 - PPT_BAR_X1} height={PPT_H}
              rx={2} fill="#1e293b" stroke="#334155" strokeWidth={0.8}
            />
            {/* remplissage */}
            <rect
              x={PPT_BAR_X1} y={PPT_Y}
              width={pptBarFill} height={PPT_H}
              rx={2} fill={COLOR_AMBER} fillOpacity={0.8}
            />
            <title>{pptTooltip}</title>
          </g>
        )}

        {/* ── Point de branchement ── */}
        {bpFound != null && pptScore != null && (
          <g style={{ cursor: "help" }}>
            <circle
              cx={PPT_BAR_X1 + (PPT_BAR_X2 - PPT_BAR_X1) * 0.38}
              cy={BP_CY}
              r={4.5}
              fill={bpFound ? COLOR_GREEN : "#475569"}
              stroke={bpFound ? "#14532d" : "#1e293b"}
              strokeWidth={1}
            />
            <title>{bpTooltip}</title>
          </g>
        )}

        {/* ── Label brin ── */}
        {strand && (
          <text
            x={W - MARGIN} y={H - 4}
            textAnchor="end" fontSize={9}
            fill={COLOR_TEXT_MUTED} fontFamily="monospace"
          >
            {strand === "+" ? "5′ → 3′ (+)" : "3′ ← 5′ (−)"}
          </text>
        )}
      </svg>
    </div>
  );
}
