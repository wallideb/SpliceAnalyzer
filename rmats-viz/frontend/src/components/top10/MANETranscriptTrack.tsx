"use client";

/**
 * MANETranscriptTrack
 * ====================
 * Linear diagram of the MANE Select transcript with the skipped exon
 * highlighted.  Uses a "compressed intron" layout: exon widths are
 * proportional to their size in nucleotides, while introns are drawn as
 * fixed-width connectors — similar to UCSC Genome Browser style.
 *
 * Data is fetched on demand from GET /api/v1/splice/mane_transcript/{eventId}.
 */

import { useQuery } from "@tanstack/react-query";
import { getMANETranscript } from "@/lib/api/splice";
import { useT } from "@/contexts/LanguageContext";
import type { MANEExon } from "@/types/splice";

// ---------------------------------------------------------------------------
// Layout constants
// ---------------------------------------------------------------------------

const SVG_W          = 800;  // viewBox width
const EXON_H         = 14;   // exon rectangle height
const INTRON_GAP_W   = 16;   // fixed width for each intron connector
const INTRON_LINE_H  = 2;    // thin line height for intron
const LABEL_H        = 14;   // height below track for labels
const SVG_H          = EXON_H + LABEL_H + 8;
const EXON_Y         = 4;
const INTRON_Y       = EXON_Y + EXON_H / 2;

// Allocate horizontal space for all exon widths (proportional, min 4 px)
const MIN_EXON_PX = 4;
const MAX_EXON_PX = 60;

// Colors
const COLOR_EXON    = "#94a3b8";   // default exon
const COLOR_SKIPPED = "#6366f1";   // skipped (highlighted) exon
const COLOR_INTRON  = "#475569";
const COLOR_MUTED   = "#64748b";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Map nucleotide size to pixel width (log-ish scaling, clamped). */
function exonPx(size: number, minSz: number, maxSz: number): number {
  if (maxSz <= minSz) return MIN_EXON_PX;
  const t = Math.log1p(size - minSz) / Math.log1p(maxSz - minSz);
  return MIN_EXON_PX + t * (MAX_EXON_PX - MIN_EXON_PX);
}

function formatCoord(v: number): string {
  return v.toLocaleString();
}

// ---------------------------------------------------------------------------
// Diagram sub-component
// ---------------------------------------------------------------------------

function TranscriptDiagram({
  exons,
  exonRank,
  strand,
  skippedStart,
  skippedEnd,
  transcriptId,
}: {
  exons: MANEExon[];
  exonRank: number | null;
  strand: string | null;
  skippedStart: number | null;
  skippedEnd: number | null;
  transcriptId: string;
}) {
  const t = useT();
  if (!exons.length) return null;

  // Render in transcript order (5'→3' = left→right) for both strands.
  // Backend returns exons sorted ascending by genomic position (index 0 = lowest coord).
  // For minus-strand genes the transcript runs high→low genomically, so we reverse
  // the array before layout so left = 5' end and right = 3' end in all cases.
  const orderedExons = strand === "-" ? [...exons].reverse() : exons;

  const minSz = Math.min(...orderedExons.map((e) => e.size));
  const maxSz = Math.max(...orderedExons.map((e) => e.size));

  // Calculate per-exon pixel widths
  const widths = orderedExons.map((e) => exonPx(e.size, minSz, maxSz));

  // Scale so total fits in SVG_W (accounting for intron gaps)
  const totalExonPx = widths.reduce((a, b) => a + b, 0);
  const totalIntronPx = (orderedExons.length - 1) * INTRON_GAP_W;
  const totalRaw = totalExonPx + totalIntronPx;
  const scale = totalRaw > SVG_W ? SVG_W / totalRaw : 1;

  // Determine skipped exon index in orderedExons (transcript order, 5'→3').
  // exonRank is 1-based in transcript order, so the 0-based index is always
  // exonRank - 1 regardless of strand (because orderedExons is already oriented).
  // Coordinate-overlap fallback (when exonRank is null) also searches orderedExons.
  const skippedIdx = (() => {
    if (exonRank !== null) return exonRank - 1;
    if (skippedStart !== null && skippedEnd !== null) {
      let best = -1;
      let bestOv = 0;
      orderedExons.forEach((e, i) => {
        const ov = Math.max(0, Math.min(skippedEnd, e.end) - Math.max(skippedStart, e.start));
        if (ov > bestOv) { bestOv = ov; best = i; }
      });
      return best;
    }
    return -1;
  })();

  // Build layout (left = 5' end, right = 3' end in all cases)
  let curX = 0;
  const blocks: { x: number; w: number; isSkipped: boolean; exon: MANEExon; idx: number }[] = [];

  orderedExons.forEach((exon, i) => {
    const w = widths[i] * scale;
    blocks.push({ x: curX, w, isSkipped: i === skippedIdx, exon, idx: i });
    curX += w;
    if (i < orderedExons.length - 1) curX += INTRON_GAP_W * scale;
  });

  const totalW = curX;

  return (
    <div>
      <div className="flex items-baseline gap-2 mb-1.5">
        <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
          {t("maneTrack.title")}
        </p>
        <code className="text-[9px] text-blue-500 dark:text-blue-400 font-mono">
          {transcriptId}
        </code>
      </div>

      <div style={{ overflowX: "auto" }}>
        <svg
          viewBox={`0 0 ${Math.ceil(totalW)} ${SVG_H}`}
          style={{ width: Math.ceil(totalW), height: SVG_H, display: "block", overflow: "visible" }}
          aria-label={t("maneTrack.title")}
        >
          {/* Backbone line */}
          <line
            x1={0}
            y1={INTRON_Y}
            x2={Math.ceil(totalW)}
            y2={INTRON_Y}
            stroke={COLOR_INTRON}
            strokeWidth={INTRON_LINE_H}
          />

          {blocks.map(({ x, w, isSkipped, exon, idx }) => {
            // Transcript rank (1-based, 5'→3') — idx is already in transcript order.
            const txRank = idx + 1;
            const tooltip = [
              t("maneTrack.exonLabel", { rank: txRank, total: orderedExons.length }),
              t("maneTrack.sizeLabel", { size: exon.size.toLocaleString() }),
              t("maneTrack.coordsLabel", { start: formatCoord(exon.start), end: formatCoord(exon.end) }),
              isSkipped ? t("maneTrack.skippedLabel") : null,
            ].filter(Boolean).join("\n");

            return (
              <g key={idx} style={{ cursor: "help" }}>
                <title>{tooltip}</title>
                <rect
                  x={x}
                  y={EXON_Y}
                  width={Math.max(2, w)}
                  height={EXON_H}
                  rx={isSkipped ? 3 : 2}
                  fill={isSkipped ? COLOR_SKIPPED : COLOR_EXON}
                  stroke={isSkipped ? "#4338ca" : undefined}
                  strokeWidth={isSkipped ? 1 : 0}
                  opacity={isSkipped ? 1 : 0.75}
                />
                {/* Rank label for skipped exon — always show transcript-order rank
                    so it matches the legend "E{exonRank} / {total}" below. */}
                {isSkipped && (
                  <text
                    x={x + w / 2}
                    y={EXON_Y + EXON_H + LABEL_H - 2}
                    textAnchor="middle"
                    fontSize={7}
                    fontFamily="monospace"
                    fill={COLOR_SKIPPED}
                    fontWeight="700"
                  >
                    E{exonRank ?? txRank}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-3 mt-1 text-[9px] text-muted-foreground">
        <span className="flex items-center gap-1">
          <span className="inline-block w-4 h-2.5 rounded-sm bg-indigo-500" />
          {t("maneTrack.skippedExon")}
          {exonRank !== null && ` (E${exonRank} / ${orderedExons.length})`}
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-4 h-2.5 rounded-sm bg-slate-400/75" />
          {t("maneTrack.otherExons")}
        </span>
        <span className="text-[9px] text-muted-foreground/60 italic">
          {t("maneTrack.widthNote")}
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------

export function MANETranscriptTrack({
  eventId,
  maneTranscriptId,
  exonRank,
}: {
  eventId: string;
  maneTranscriptId: string | null;
  exonRank: number | null;
}) {
  const t = useT();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["mane-transcript", eventId],
    queryFn: () => getMANETranscript(eventId),
    enabled: !!maneTranscriptId,
    staleTime: 30 * 60 * 1000,
    retry: false,
  });

  if (!maneTranscriptId) {
    return (
      <div className="mt-3 p-3 rounded-lg bg-muted/30 border border-border">
        <p className="text-[9px] text-muted-foreground italic">
          {t("maneTrack.notFound")}
        </p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="mt-3 p-3 rounded-lg bg-muted/30 border border-border">
        <div className="h-3 w-32 rounded bg-muted animate-pulse mb-2" />
        <div className="h-5 rounded bg-muted animate-pulse" />
      </div>
    );
  }

  if (isError || !data || !data.exons.length) {
    return (
      <div className="mt-3 p-3 rounded-lg bg-muted/30 border border-border">
        <p className="text-[9px] text-muted-foreground">
          {t("maneTrack.structureNotAvailable")}{" "}
          <code className="font-mono text-blue-500">{maneTranscriptId}</code>
        </p>
      </div>
    );
  }

  return (
    <div className="mt-3 p-3 rounded-lg bg-muted/30 border border-border">
      <TranscriptDiagram
        exons={data.exons}
        exonRank={exonRank}
        strand={data.strand}
        skippedStart={data.skipped_start}
        skippedEnd={data.skipped_end}
        transcriptId={data.transcript_id ?? maneTranscriptId}
      />
    </div>
  );
}
