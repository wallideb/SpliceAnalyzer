"use client";

/**
 * ExonDiagram — Publication-style SVG exon-skipping diagram (full-width)
 * ========================================================================
 * viewBox 0 0 900 200 — chaque zone est interactive (hover + title tooltip).
 *
 * Annotations interactives superposées sur le schéma :
 *  - Arc           → FDR, ΔΨ, p-value, PSI groupe 1 & 2
 *  - Exon sauté    → coordonnées, taille, frame class, MANE, rang exon
 *  - Exons flanc.  → coordonnées
 *  - Zone 5'SS     → séquence 9 nt colorée au survol (GT mis en valeur)
 *  - Zone 3'SS     → séquence 23 nt colorée au survol (AG mis en valeur)
 *  - Barre PPT     → score + strip nucléotidique compact
 *  - Point BP      → trouvé/non trouvé, distance, motif YNYURAY
 *  - Badge Frame   → class, transcrit MANE, rang exon
 */

import { useState } from "react";
import { useT } from "@/contexts/LanguageContext";

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
  upstreamDonorSeq?: string | null;
  downstreamAcceptorSeq?: string | null;
  pptScore?: number | null;
  pptSeq?: string | null;
  bpFound?: boolean | null;
  bpDistance?: number | null;
  group1Label?: string;
  group2Label?: string;
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
// Layout constants (SVG user units, viewBox 900×200)
// ---------------------------------------------------------------------------

const W = 900;
const H = 220;

const EXON_Y   = 78;
const EXON_H   = 32;
const INTRON_Y = EXON_Y + EXON_H / 2;
const LABEL_Y  = EXON_Y + EXON_H + 16;

const FLANK_W  = 90;
const SKIP_W   = 160;
const MARGIN   = 30;

const LEFT_EXON_X     = MARGIN;
const LEFT_EXON_RIGHT = LEFT_EXON_X + FLANK_W;   // 120
const RIGHT_EXON_X    = W - MARGIN - FLANK_W;     // 780
const RIGHT_EXON_LEFT = RIGHT_EXON_X;             // 780

const SKIP_X     = (W - SKIP_W) / 2;  // 370
const SKIP_RIGHT = SKIP_X + SKIP_W;   // 530

const ARC_TOP_Y = 14;

// Site donor / acceptor indicator zones
const SITE_W = 20;
const SITE_H = EXON_H + 10;

// PPT bar (bottom area)
const PPT_Y      = 160;
const PPT_H      = 8;
const PPT_BAR_X1 = 560;
const PPT_BAR_X2 = RIGHT_EXON_LEFT; // 780
const BP_CY      = PPT_Y + PPT_H / 2;

// Annotation strip (below exon, above intron labels) — for hovered sequences
const SEQ_STRIP_Y = 114;
const SEQ_CELL_H  = 12;

// Nucleotide colours (consistent with SpliceSiteTrack)
const NUC_COLOR: Record<string, string> = {
  A: "#f97316",  // orange
  G: "#8b5cf6",  // violet
  C: "#3b82f6",  // blue
  T: "#06b6d4",  // cyan
  N: "#94a3b8",  // gray
  Y: "#3b82f6",
  R: "#f97316",
  U: "#06b6d4",
};

function nucColor(base: string): string {
  return NUC_COLOR[base.toUpperCase()] ?? "#94a3b8";
}

// Donor: positions -3,-2,-1 | +1,+2,...,+6 (GT at idx 3,4)
// Acceptor: positions -20...,-1 | +1,+2,+3 (AG at idx 21,22 i.e. 17,18 in 0-based -20 slice)
const DONOR_GT_IDX    = new Set([3, 4]);
const ACCEPTOR_AG_IDX = new Set([18, 19]); // 0-based in 23-nt sequence: AG at positions -2,-1

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
// NucStrip — row of coloured nucleotide cells (SVG inline)
// ---------------------------------------------------------------------------

function NucStrip({
  seq,
  x,
  y,
  cellW,
  cellH,
  highlightIdxs,
}: {
  seq: string;
  x: number;
  y: number;
  cellW: number;
  cellH: number;
  highlightIdxs?: Set<number>;
}) {
  return (
    <g>
      {/* Background panel */}
      <rect
        x={x - 2} y={y - 1}
        width={seq.length * cellW + 4} height={cellH + 2}
        rx={2} fill="var(--svg-panel-bg)" fillOpacity={0.85}
      />
      {seq.toUpperCase().split("").map((base, i) => {
        const cx = x + i * cellW;
        const highlight = highlightIdxs?.has(i) ?? false;
        const bg = highlight ? "var(--svg-highlight-bg)" : nucColor(base);
        return (
          <g key={i}>
            <rect
              x={cx} y={y}
              width={cellW - 1} height={cellH}
              rx={1}
              fill={bg}
              fillOpacity={highlight ? 0.95 : 0.75}
            />
            <text
              x={cx + (cellW - 1) / 2} y={y + cellH * 0.74}
              textAnchor="middle"
              fontSize={cellH * 0.64}
              fill="white"
              fontFamily="monospace"
              fontWeight={highlight ? "bold" : "normal"}
            >
              {base}
            </text>
          </g>
        );
      })}
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
  upstreamDonorSeq,
  downstreamAcceptorSeq,
  pptScore,
  pptSeq,
  bpFound,
  bpDistance,
  group1Label,
  group2Label,
}: ExonDiagramProps) {
  const t = useT();

  // Hover state: which annotation element is expanded
  const [hoveredEl, setHoveredEl] = useState<"donor" | "acceptor" | "ppt" | "bp" | "upDonor" | "dnAcceptor" | null>(null);

  const delta    = incLevelDifference ?? 0;
  // ΔΨ < 0 → more exon skipping in group 1 (patients) → RED
  // ΔΨ > 0 → more exon skipping in group 2 (controls) → BLUE
  const arcColor = delta < 0 ? COLOR_RED : COLOR_BLUE;
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
    fdr !== null              ? `FDR: ${fmtPval(fdr)}`                                                    : null,
    incLevelDifference !== null ? `ΔΨ: ${fmtDelta(incLevelDifference)}`                                   : null,
    pValue !== null           ? `p-value: ${fmtPval(pValue)}`                                             : null,
    psi1 != null              ? `PSI ${group1Label ?? t("exonDiagram.psiGroup1Label")} (mean): ${psi1.toFixed(3)}` : null,
    psi2 != null              ? `PSI ${group2Label ?? t("exonDiagram.psiGroup2Label")} (mean): ${psi2.toFixed(3)}` : null,
  ].filter(Boolean).join("\n");

  const skipTooltip = [
    exonSize !== null         ? t("exonDiagram.size", { n: fmtSize(exonSize) })                           : null,
    exonStart != null && exonEnd != null
      ? t("exonDiagram.coords", { start: fmtCoord(exonStart), end: fmtCoord(exonEnd) })                  : null,
    frameClass                ? `Frame: ${FRAME_LABELS[frameClass] ?? frameClass}`                        : null,
    maneTranscriptId          ? `MANE: ${maneTranscriptId}`                                               : null,
    exonRank != null          ? t("exonDiagram.exonRank", { n: exonRank })                                : null,
  ].filter(Boolean).join("\n");

  const upstreamTooltip = [
    t("exonDiagram.upstreamFlankingExon"),
    upstreamExonStart != null && upstreamExonEnd != null
      ? t("exonDiagram.coords", { start: fmtCoord(upstreamExonStart), end: fmtCoord(upstreamExonEnd) })  : null,
    upstreamDonorSeq ? t("exonDiagram.hoverForSeq") : null,
  ].filter(Boolean).join("\n");

  const downstreamTooltip = [
    t("exonDiagram.downstreamFlankingExon"),
    downstreamExonStart != null && downstreamExonEnd != null
      ? t("exonDiagram.coords", { start: fmtCoord(downstreamExonStart), end: fmtCoord(downstreamExonEnd) }) : null,
    downstreamAcceptorSeq ? t("exonDiagram.hoverForSeq") : null,
  ].filter(Boolean).join("\n");

  const donorTooltip = donorSeq
    ? [
        donorIsGt === false ? t("exonDiagram.donor5ssNonGt") : t("exonDiagram.donor5ssCanonical"),
        t("exonDiagram.seq9nt", { seq: `${donorSeq.slice(0, 3)}[GT]${donorSeq.slice(5)}` }),
        t("exonDiagram.hoverForSeq"),
      ].join("\n")
    : t("exonDiagram.donor5ssNoData");

  const acceptorTooltip = acceptorSeq
    ? [
        acceptorIsAg === false ? t("exonDiagram.acceptor3ssNonAg") : t("exonDiagram.acceptor3ssCanonical"),
        t("exonDiagram.seq23nt", { seq: `…${acceptorSeq.slice(14, 19)}[AG]${acceptorSeq.slice(19)}` }),
        t("exonDiagram.hoverForSeq"),
      ].join("\n")
    : t("exonDiagram.acceptor3ssNoData");

  const pptInterpret =
    (pptScore ?? 0) >= 0.7 ? t("exonDiagram.pptStrong") :
    (pptScore ?? 0) >= 0.5 ? t("exonDiagram.pptModerate") : t("exonDiagram.pptWeak");
  const pptTooltip = [
    t("exonDiagram.pptZone"),
    pptScore != null ? t("exonDiagram.pptScore", { pct: Math.round(pptScore * 100), interp: pptInterpret }) : null,
    pptSeq   ? t("exonDiagram.pptSeq", { seq: `${pptSeq.slice(0, 24)}…` }) : null,
    t("exonDiagram.hoverForNuc"),
  ].filter(Boolean).join("\n");

  const bpTooltip = bpFound
    ? `${t("exonDiagram.bp")}\n${t("exonDiagram.bpFound", { dist: bpDistance ?? "?" })}\n${t("exonDiagram.bpHoverDetail")}`
    : `${t("exonDiagram.bp")}\n${t("exonDiagram.bpNotFound")}`;

  const fc           = frameClass ?? "unknown";
  const frameColors  = FRAME_COLORS[fc] ?? FRAME_COLORS.unknown;
  const frameLabel   = FRAME_LABELS[fc] ?? fc;
  const frameBadgeTooltip = [
    `Frame: ${frameLabel}`,
    maneTranscriptId ? t("exonDiagram.maneTranscript", { id: maneTranscriptId }) : t("exonDiagram.maneNotFound"),
    exonRank != null ? t("exonDiagram.exonRank", { n: exonRank }) : null,
  ].filter(Boolean).join("\n");

  // Only warn non-canonical when we actually have sequence data to prove it
  const warnDonor    = donorIsGt    === false && !!donorSeq;
  const warnAcceptor = acceptorIsAg === false && !!acceptorSeq;
  // Show "no data" state when there's no sequence at all
  const noSeqData    = !donorSeq && !acceptorSeq;

  // PPT bar width
  const pptBarFill = pptScore != null
    ? (PPT_BAR_X2 - PPT_BAR_X1) * Math.min(1, Math.max(0, pptScore))
    : 0;

  // Branch-point circle position (38% into PPT bar)
  const bpCX = PPT_BAR_X1 + (PPT_BAR_X2 - PPT_BAR_X1) * 0.38;

  // Donor site indicator bounds — at right edge of skipped exon (5'SS donor)
  const donorIndicatorX = SKIP_RIGHT - 5;
  const donorIndicatorW = SITE_W;

  // Acceptor site indicator bounds — at left edge of skipped exon (3'SS acceptor)
  const acceptorIndicatorX = SKIP_X - SITE_W + 5;
  const acceptorIndicatorW = SITE_W;

  // Hover hit area: expand the zone around indicator for easier hovering
  const HOVER_PAD = 8;

  return (
    <div className="w-full">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: "100%", display: "block" }}
        aria-label={t("exonDiagram.ariaLabel")}
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
            textAnchor="middle" fontSize={11}
            fill={arcColor} fontFamily="monospace" fontWeight="700"
          >
            {[
              fdr !== null              ? `FDR ${fmtPval(fdr)}`          : null,
              incLevelDifference !== null ? `ΔΨ ${fmtDelta(incLevelDifference)}` : null,
            ].filter(Boolean).join("  |  ")}
          </text>
        )}

        {/* ── Exon flanquant gauche ── */}
        <g
          style={{ cursor: upstreamDonorSeq ? "crosshair" : "help" }}
          onMouseEnter={upstreamDonorSeq ? () => setHoveredEl("upDonor") : undefined}
          onMouseLeave={upstreamDonorSeq ? () => setHoveredEl(null) : undefined}
        >
          <rect x={LEFT_EXON_X} y={EXON_Y} width={FLANK_W} height={EXON_H} rx={4}
            fill={COLOR_FLANK}
            stroke={hoveredEl === "upDonor" ? COLOR_GREEN : "none"}
            strokeWidth={hoveredEl === "upDonor" ? 1.5 : 0}
          />
          <title>{upstreamTooltip}</title>
        </g>
        <text
          x={LEFT_EXON_X + FLANK_W / 2} y={LABEL_Y + 2}
          textAnchor="middle" fontSize={10}
          fill={COLOR_TEXT_MUTED} fontFamily="sans-serif"
        >
          {t("exonDiagram.upstreamFlankingExon")}
        </text>

        {/* ── Zone Donor (5'SS) — compact + hover expand ── */}
        <g
          style={{ cursor: "crosshair" }}
          onMouseEnter={() => setHoveredEl("donor")}
          onMouseLeave={() => setHoveredEl(null)}
        >
          {/* Hit area (wider than indicator) */}
          <rect
            x={donorIndicatorX - HOVER_PAD}
            y={EXON_Y - HOVER_PAD}
            width={donorIndicatorW + HOVER_PAD * 2}
            height={SITE_H + HOVER_PAD * 2}
            fill="transparent"
          />
          {/* Indicator box */}
          <rect
            x={donorIndicatorX}
            y={EXON_Y - 4}
            width={donorIndicatorW}
            height={SITE_H}
            rx={2}
            fill={warnDonor ? COLOR_WARN : !donorSeq ? COLOR_TEXT_MUTED : COLOR_GREEN}
            fillOpacity={hoveredEl === "donor" ? 0.4 : 0.22}
            stroke={warnDonor ? COLOR_WARN : !donorSeq ? COLOR_TEXT_MUTED : COLOR_GREEN}
            strokeWidth={hoveredEl === "donor" ? 1.5 : 1}
          />
          {/* GT / warn / no-data label inside box */}
          <text
            x={donorIndicatorX + donorIndicatorW / 2}
            y={EXON_Y + EXON_H / 2 + 3}
            textAnchor="middle" fontSize={!donorSeq ? 7 : 8.5}
            fill={warnDonor ? COLOR_WARN : !donorSeq ? COLOR_TEXT_MUTED : COLOR_GREEN}
            fontFamily="monospace" fontWeight="bold"
          >
            {warnDonor ? "!GT" : !donorSeq ? "?" : "GT"}
          </text>
          <title>{donorTooltip}</title>
        </g>

        {/* 5'SS label above donor */}
        <text
          x={donorIndicatorX + donorIndicatorW / 2}
          y={EXON_Y - 7}
          textAnchor="middle" fontSize={8}
          fill={warnDonor ? COLOR_WARN : !donorSeq ? COLOR_TEXT_MUTED : COLOR_GREEN}
          fontFamily="monospace" fontWeight="700"
        >
          5&apos;SS
        </text>

        {warnDonor && (
          <text x={SKIP_RIGHT + 2} y={EXON_Y - 13} fontSize={8} fill={COLOR_WARN} fontFamily="sans-serif">
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

        {/* ── Zone Acceptor (3'SS) — compact + hover expand ── */}
        <g
          style={{ cursor: "crosshair" }}
          onMouseEnter={() => setHoveredEl("acceptor")}
          onMouseLeave={() => setHoveredEl(null)}
        >
          {/* Hit area */}
          <rect
            x={acceptorIndicatorX - HOVER_PAD}
            y={EXON_Y - HOVER_PAD}
            width={acceptorIndicatorW + HOVER_PAD * 2}
            height={SITE_H + HOVER_PAD * 2}
            fill="transparent"
          />
          {/* Indicator box */}
          <rect
            x={acceptorIndicatorX}
            y={EXON_Y - 4}
            width={acceptorIndicatorW}
            height={SITE_H}
            rx={2}
            fill={warnAcceptor ? COLOR_WARN : !acceptorSeq ? COLOR_TEXT_MUTED : COLOR_GREEN}
            fillOpacity={hoveredEl === "acceptor" ? 0.4 : 0.22}
            stroke={warnAcceptor ? COLOR_WARN : !acceptorSeq ? COLOR_TEXT_MUTED : COLOR_GREEN}
            strokeWidth={hoveredEl === "acceptor" ? 1.5 : 1}
          />
          {/* AG / warn / no-data label inside box */}
          <text
            x={acceptorIndicatorX + acceptorIndicatorW / 2}
            y={EXON_Y + EXON_H / 2 + 3}
            textAnchor="middle" fontSize={!acceptorSeq ? 7 : 8.5}
            fill={warnAcceptor ? COLOR_WARN : !acceptorSeq ? COLOR_TEXT_MUTED : COLOR_GREEN}
            fontFamily="monospace" fontWeight="bold"
          >
            {warnAcceptor ? "!AG" : !acceptorSeq ? "?" : "AG"}
          </text>
          <title>{acceptorTooltip}</title>
        </g>

        {/* 3'SS label above acceptor */}
        <text
          x={acceptorIndicatorX + acceptorIndicatorW / 2}
          y={EXON_Y - 7}
          textAnchor="middle" fontSize={8}
          fill={warnAcceptor ? COLOR_WARN : !acceptorSeq ? COLOR_TEXT_MUTED : COLOR_GREEN}
          fontFamily="monospace" fontWeight="700"
        >
          3&apos;SS
        </text>

        {warnAcceptor && (
          <text x={SKIP_X - 2} y={EXON_Y - 13} textAnchor="end" fontSize={8} fill={COLOR_WARN} fontFamily="sans-serif">
            ⚠ non-AG
          </text>
        )}

        {/* ── Exon flanquant droit ── */}
        <g
          style={{ cursor: downstreamAcceptorSeq ? "crosshair" : "help" }}
          onMouseEnter={downstreamAcceptorSeq ? () => setHoveredEl("dnAcceptor") : undefined}
          onMouseLeave={downstreamAcceptorSeq ? () => setHoveredEl(null) : undefined}
        >
          <rect x={RIGHT_EXON_X} y={EXON_Y} width={FLANK_W} height={EXON_H} rx={4}
            fill={COLOR_FLANK}
            stroke={hoveredEl === "dnAcceptor" ? COLOR_GREEN : "none"}
            strokeWidth={hoveredEl === "dnAcceptor" ? 1.5 : 0}
          />
          <title>{downstreamTooltip}</title>
        </g>
        <text
          x={RIGHT_EXON_X + FLANK_W / 2} y={LABEL_Y + 2}
          textAnchor="middle" fontSize={10}
          fill={COLOR_TEXT_MUTED} fontFamily="sans-serif"
        >
          {t("exonDiagram.downstreamFlankingExon")}
        </text>

        {/* ── Barre PPT — zone hover ── */}
        {pptScore != null && (
          <g
            style={{ cursor: "crosshair" }}
            onMouseEnter={() => setHoveredEl("ppt")}
            onMouseLeave={() => setHoveredEl(null)}
          >
            {/* Hit area */}
            <rect
              x={PPT_BAR_X1 - 40} y={PPT_Y - 6}
              width={PPT_BAR_X2 - PPT_BAR_X1 + 48} height={PPT_H + 12}
              fill="transparent"
            />
            {/* Label */}
            <text
              x={PPT_BAR_X1 - 5} y={PPT_Y + PPT_H - 1}
              textAnchor="end" fontSize={8}
              fill={COLOR_TEXT_MUTED} fontFamily="monospace"
            >
              PPT {Math.round(pptScore * 100)}%
            </text>
            {/* Direction arrow + label */}
            <text
              x={PPT_BAR_X1 + 2} y={PPT_Y - 3}
              fontSize={6.5} fill={COLOR_AMBER}
              fontFamily="monospace"
            >
              ←47nt→ 3&apos;SS
            </text>
            {/* Fond */}
            <rect
              x={PPT_BAR_X1} y={PPT_Y}
              width={PPT_BAR_X2 - PPT_BAR_X1} height={PPT_H}
              rx={2} fill="var(--svg-panel-bg)" stroke="var(--svg-panel-border)" strokeWidth={0.8}
            />
            {/* Remplissage */}
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
          <g
            style={{ cursor: "crosshair" }}
            onMouseEnter={() => setHoveredEl("bp")}
            onMouseLeave={() => setHoveredEl(null)}
          >
            {/* Hit area */}
            <circle cx={bpCX} cy={BP_CY} r={12} fill="transparent" />
            {/* Circle */}
            <circle
              cx={bpCX}
              cy={BP_CY}
              r={4.5}
              fill={bpFound ? COLOR_GREEN : "var(--svg-panel-border)"}
              stroke={bpFound ? "#14532d" : "var(--svg-panel-bg)"}
              strokeWidth={hoveredEl === "bp" ? 2 : 1}
            />
            {/* BP label next to circle */}
            <text
              x={bpCX + 7} y={BP_CY + 3}
              fontSize={8} fill={bpFound ? COLOR_GREEN : COLOR_TEXT_MUTED}
              fontFamily="monospace" fontWeight="600"
            >
              BP{bpFound && bpDistance ? ` ~${bpDistance}nt` : "?"}
            </text>
            <title>{bpTooltip}</title>
          </g>
        )}


        {/* ══════════════════════════════════════════════════════════════════
            HOVER OVERLAYS — rendered last so they appear on top
        ══════════════════════════════════════════════════════════════════ */}

        {/* ── Donor hover: séquence 9 nt complète ── */}
        {hoveredEl === "donor" && donorSeq && (() => {
          const stripX = SKIP_RIGHT - 3 * 8; // align exon boundary with position -1/+1
          return (
          <g>
            {/* Position axis above strip */}
            {[-3, -2, -1, 1, 2, 3, 4, 5, 6].map((pos, i) => (
              <text
                key={i}
                x={stripX + i * 8 + 3}
                y={SEQ_STRIP_Y - 2}
                textAnchor="middle" fontSize={7}
                fill={DONOR_GT_IDX.has(i) ? COLOR_AMBER : COLOR_TEXT_MUTED}
                fontFamily="monospace"
              >
                {pos > 0 ? `+${pos}` : pos}
              </text>
            ))}
            <NucStrip
              seq={donorSeq}
              x={stripX}
              y={SEQ_STRIP_Y}
              cellW={8}
              cellH={SEQ_CELL_H}
              highlightIdxs={DONOR_GT_IDX}
            />
            {/* Boundary line */}
            <line
              x1={stripX + 3 * 8} y1={SEQ_STRIP_Y - 1}
              x2={stripX + 3 * 8} y2={SEQ_STRIP_Y + SEQ_CELL_H + 1}
              stroke={COLOR_AMBER} strokeWidth={1} strokeDasharray="2 1"
            />
            {/* Label */}
            <text
              x={stripX + 9 * 8 + 5} y={SEQ_STRIP_Y + SEQ_CELL_H * 0.7}
              fontSize={7} fill={COLOR_GREEN} fontFamily="monospace"
            >
              5&apos;SS
            </text>
          </g>
          );
        })()}

        {/* ── Acceptor hover: séquence 23 nt complète ── */}
        {hoveredEl === "acceptor" && acceptorSeq && (() => {
          const stripX = SKIP_X - 20 * 6.5; // position so that exon boundary aligns with pos -1/+1
          return (
          <g>
            {/* Position axis above strip — last 23 positions before AG then +1,+2,+3 */}
            {Array.from({ length: 23 }, (_, i) => {
              const posNum = i < 20 ? -(20 - i) : i - 19;
              return (
                <text
                  key={i}
                  x={stripX + i * 6.5 + 2.5}
                  y={SEQ_STRIP_Y - 2}
                  textAnchor="middle" fontSize={6.5}
                  fill={ACCEPTOR_AG_IDX.has(i) ? COLOR_AMBER : COLOR_TEXT_MUTED}
                  fontFamily="monospace"
                >
                  {posNum > 0 ? `+${posNum}` : posNum}
                </text>
              );
            })}
            <NucStrip
              seq={acceptorSeq}
              x={stripX}
              y={SEQ_STRIP_Y}
              cellW={6.5}
              cellH={SEQ_CELL_H}
              highlightIdxs={ACCEPTOR_AG_IDX}
            />
            {/* Boundary line */}
            <line
              x1={stripX + 20 * 6.5} y1={SEQ_STRIP_Y - 1}
              x2={stripX + 20 * 6.5} y2={SEQ_STRIP_Y + SEQ_CELL_H + 1}
              stroke={COLOR_AMBER} strokeWidth={1} strokeDasharray="2 1"
            />
            {/* Label */}
            <text
              x={stripX - 5} y={SEQ_STRIP_Y + SEQ_CELL_H * 0.7}
              textAnchor="end" fontSize={7} fill={COLOR_GREEN} fontFamily="monospace"
            >
              3&apos;SS
            </text>
          </g>
          );
        })()}

        {/* ── PPT hover: strip nucléotidique compact ── */}
        {hoveredEl === "ppt" && pptSeq && (
          <g>
            {/* Show last 30nt of PPT (closest to 3'SS) as compact strip */}
            {(() => {
              const displaySeq = pptSeq.length > 30
                ? pptSeq.slice(pptSeq.length - 30)
                : pptSeq;
              const cellW = Math.min(6, (PPT_BAR_X2 - PPT_BAR_X1) / displaySeq.length);
              const startX = PPT_BAR_X2 - displaySeq.length * cellW;
              return (
                <>
                  <text
                    x={startX} y={PPT_Y - 3}
                    fontSize={6} fill={COLOR_TEXT_MUTED} fontFamily="monospace"
                    textAnchor="start"
                  >
                    {pptSeq.length > 30 ? "…" : ""}
                  </text>
                  <NucStrip
                    seq={displaySeq}
                    x={startX}
                    y={PPT_Y}
                    cellW={cellW}
                    cellH={PPT_H}
                    highlightIdxs={undefined}
                  />
                </>
              );
            })()}
            <text
              x={PPT_BAR_X1 - 5} y={PPT_Y + PPT_H - 1}
              textAnchor="end" fontSize={8}
              fill={COLOR_AMBER} fontFamily="monospace" fontWeight="600"
            >
              {pptSeq.length} nt Y/R
            </text>
          </g>
        )}

        {/* ── BP hover: motif + détails ── */}
        {hoveredEl === "bp" && bpFound != null && (
          <g>
            <rect
              x={bpCX - 30} y={PPT_Y - 22}
              width={90} height={18}
              rx={3} fill="var(--svg-panel-bg)" stroke={bpFound ? COLOR_GREEN : "var(--svg-panel-border)"}
              strokeWidth={0.8} fillOpacity={0.95}
            />
            <text
              x={bpCX + 15} y={PPT_Y - 11}
              textAnchor="middle" fontSize={7}
              fill={bpFound ? COLOR_GREEN : COLOR_TEXT_MUTED}
              fontFamily="monospace"
            >
              {bpFound
                ? `YNYURAY — ${t("exonDiagram.bpFound", { dist: bpDistance ?? "?" })}`
                : `YNYURAY — ${t("exonDiagram.bpNotFound")}`}
            </text>
          </g>
        )}

        {/* ── Upstream flanking exon 5'SS hover: 9 nt donor sequence ── */}
        {hoveredEl === "upDonor" && upstreamDonorSeq && (() => {
          const stripX = LEFT_EXON_RIGHT - 3 * 8; // align exon boundary with pos -1/+1
          return (
          <g>
            {[-3, -2, -1, 1, 2, 3, 4, 5, 6].map((pos, i) => (
              <text
                key={i}
                x={stripX + i * 8 + 3}
                y={SEQ_STRIP_Y - 2}
                textAnchor="middle" fontSize={7}
                fill={DONOR_GT_IDX.has(i) ? COLOR_AMBER : COLOR_TEXT_MUTED}
                fontFamily="monospace"
              >
                {pos > 0 ? `+${pos}` : pos}
              </text>
            ))}
            <NucStrip
              seq={upstreamDonorSeq.slice(0, 9)}
              x={stripX}
              y={SEQ_STRIP_Y}
              cellW={8}
              cellH={SEQ_CELL_H}
              highlightIdxs={DONOR_GT_IDX}
            />
            {/* Boundary line */}
            <line
              x1={stripX + 3 * 8} y1={SEQ_STRIP_Y - 1}
              x2={stripX + 3 * 8} y2={SEQ_STRIP_Y + SEQ_CELL_H + 1}
              stroke={COLOR_AMBER} strokeWidth={1} strokeDasharray="2 1"
            />
            <text
              x={stripX + 9 * 8 + 5} y={SEQ_STRIP_Y + SEQ_CELL_H * 0.7}
              fontSize={7} fill={COLOR_GREEN} fontFamily="monospace"
            >
              5&apos;SS flank
            </text>
          </g>
          );
        })()}

        {/* ── Downstream flanking exon 3'SS hover: 23 nt acceptor sequence ── */}
        {hoveredEl === "dnAcceptor" && downstreamAcceptorSeq && (() => {
          const seq23 = downstreamAcceptorSeq.slice(-23);
          const stripX = RIGHT_EXON_X - 20 * 6.5; // align exon boundary with pos -1/+1
          return (
          <g>
            {Array.from({ length: 23 }, (_, i) => {
              const posNum = i < 20 ? -(20 - i) : i - 19;
              return (
                <text
                  key={i}
                  x={stripX + i * 6.5 + 2.5}
                  y={SEQ_STRIP_Y - 2}
                  textAnchor="middle" fontSize={6.5}
                  fill={ACCEPTOR_AG_IDX.has(i) ? COLOR_AMBER : COLOR_TEXT_MUTED}
                  fontFamily="monospace"
                >
                  {posNum > 0 ? `+${posNum}` : posNum}
                </text>
              );
            })}
            <NucStrip
              seq={seq23}
              x={stripX}
              y={SEQ_STRIP_Y}
              cellW={6.5}
              cellH={SEQ_CELL_H}
              highlightIdxs={ACCEPTOR_AG_IDX}
            />
            {/* Boundary line */}
            <line
              x1={stripX + 20 * 6.5} y1={SEQ_STRIP_Y - 1}
              x2={stripX + 20 * 6.5} y2={SEQ_STRIP_Y + SEQ_CELL_H + 1}
              stroke={COLOR_AMBER} strokeWidth={1} strokeDasharray="2 1"
            />
            <text
              x={stripX - 5} y={SEQ_STRIP_Y + SEQ_CELL_H * 0.7}
              textAnchor="end" fontSize={7} fill={COLOR_GREEN} fontFamily="monospace"
            >
              3&apos;SS flank
            </text>
          </g>
          );
        })()}

      </svg>
    </div>
  );
}
