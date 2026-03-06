"use client";

/**
 * SpliceView — per-card splice signal view (mode "splice")
 * =========================================================
 * Displayed inside each AnnotatedCard when the user selects the "Sites
 * consensus" sidebar tab.
 *
 * Shows:
 *  - Exon size + upstream/downstream intron sizes
 *  - Frame class badge (in_frame / frameshift / non_coding / unknown)
 *  - MANE transcript + exon rank
 *  - Donor site (9 nt): xxx [GT] yyyy — GT highlighted
 *  - Acceptor site (23 nt): ………………… [AG] xxx — AG highlighted
 *  - PPT sequence with C/T coloured orange, score bar
 *  - Branch-point: found / not found + distance to 3'SS
 *
 * For non-SE events displays a brief notice.
 * If features not yet computed shows a "Calculate" button.
 */

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getEventSpliceFeature, computeSpliceFeatures } from "@/lib/api/splice";
import type { SplicingEvent } from "@/types/event";

// ---------------------------------------------------------------------------
// Frame badge
// ---------------------------------------------------------------------------

const FRAME_STYLE: Record<string, string> = {
  in_frame:   "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300 border-green-200 dark:border-green-700",
  frameshift: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300 border-red-200 dark:border-red-700",
  non_coding: "bg-slate-100 text-slate-600 dark:bg-slate-700/40 dark:text-slate-300 border-slate-300 dark:border-slate-600",
  unknown:    "bg-muted text-muted-foreground border-border",
};
const FRAME_LABEL: Record<string, string> = {
  in_frame:   "In-frame",
  frameshift: "Frameshift",
  non_coding: "Non codant",
  unknown:    "Inconnu",
};

// ---------------------------------------------------------------------------
// Sequence display with highlighted dinucleotide
// ---------------------------------------------------------------------------

function SeqDisplay({
  seq,
  hlStart,
  hlEnd,
  label,
}: {
  seq: string;
  hlStart: number;
  hlEnd: number;
  label: string;
}) {
  const pre  = seq.slice(0, hlStart);
  const hl   = seq.slice(hlStart, hlEnd);
  const post = seq.slice(hlEnd);
  return (
    <div>
      <p className="text-[10px] text-muted-foreground mb-0.5">{label}</p>
      <code className="text-xs tracking-wider font-mono">
        <span className="text-foreground/70">{pre}</span>
        <span className="bg-green-400/30 text-green-700 dark:text-green-300 font-bold px-0.5 rounded">
          {hl}
        </span>
        <span className="text-foreground/70">{post}</span>
      </code>
    </div>
  );
}

// ---------------------------------------------------------------------------
// PPT display
// ---------------------------------------------------------------------------

function PPTDisplay({ seq, score }: { seq: string; score: number | null }) {
  return (
    <div>
      <p className="text-[10px] text-muted-foreground mb-0.5">
        Zone PPT (47 nt avant 3&apos;SS)
      </p>
      <code className="text-xs tracking-wider font-mono leading-relaxed break-all">
        {seq.split("").map((c, i) => (
          <span
            key={i}
            className={c === "C" || c === "T" ? "text-amber-600 dark:text-amber-400 font-bold" : "text-foreground/40"}
          >
            {c}
          </span>
        ))}
      </code>
      {score !== null && (
        <div className="flex items-center gap-2 mt-1">
          <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-amber-400"
              style={{ width: `${Math.round(score * 100)}%` }}
            />
          </div>
          <span className="text-[10px] font-semibold text-amber-600 dark:text-amber-400 tabular-nums">
            {Math.round(score * 100)}% Y
          </span>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Size chip
// ---------------------------------------------------------------------------

function SizeChip({ label, value, unit = "nt" }: { label: string; value: number | null; unit?: string }) {
  if (value === null) return null;
  return (
    <div className="text-center">
      <p className="text-[9px] text-muted-foreground uppercase tracking-wide">{label}</p>
      <p className="text-xs font-bold text-foreground tabular-nums">{value.toLocaleString()} {unit}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main SpliceView component
// ---------------------------------------------------------------------------

export function SpliceView({
  event: ev,
  analysisId,
}: {
  event: SplicingEvent;
  analysisId?: string;
}) {
  const qc = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["splice-feature", ev.id],
    queryFn: () => getEventSpliceFeature(ev.id),
    enabled: ev.event_type === "SE",
    staleTime: 10 * 60 * 1000,
    retry: false,
  });

  const compute = useMutation({
    mutationFn: () => computeSpliceFeatures(analysisId ?? ""),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["splice-feature", ev.id] }),
  });

  if (ev.event_type !== "SE") {
    return (
      <p className="text-xs text-muted-foreground italic">
        Analyse de sites d&apos;épissage disponible pour les évènements SE uniquement.
      </p>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-4 rounded bg-muted animate-pulse" />
        ))}
      </div>
    );
  }

  // 404 or not computed yet
  if (isError || !data) {
    return (
      <div className="flex flex-col items-center gap-3 py-4 text-center">
        <p className="text-xs text-muted-foreground">
          Features non calculées pour cet événement.
        </p>
        {analysisId && (
          <button
            onClick={() => compute.mutate()}
            disabled={compute.isPending}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50 transition-colors"
          >
            {compute.isPending ? "Calcul…" : "Calculer les features"}
          </button>
        )}
      </div>
    );
  }

  const fc = data.frame_class ?? "unknown";

  return (
    <div className="space-y-3 text-xs">

      {/* ── Sizes ── */}
      <div className="flex gap-4 justify-between px-2 py-2 rounded-lg bg-muted/30 dark:bg-slate-700/30">
        <SizeChip label="Exon sauté" value={data.exon_size} />
        <SizeChip label="Intron amont" value={data.upstream_intron_size} />
        <SizeChip label="Intron aval" value={data.downstream_intron_size} />
      </div>

      {/* ── Frame + MANE ── */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`inline-flex items-center px-2 py-0.5 rounded border text-[10px] font-bold ${FRAME_STYLE[fc]}`}>
          {FRAME_LABEL[fc] ?? fc}
        </span>
        {data.frame_region && data.frame_region !== "unknown" && (
          <span className="text-[10px] text-muted-foreground">
            région : <strong>{data.frame_region}</strong>
          </span>
        )}
        {data.mane_transcript_id && (
          <span className="text-[10px] text-muted-foreground truncate max-w-[140px]" title={data.mane_transcript_id}>
            MANE : <strong>{data.mane_transcript_id}</strong>
            {data.exon_rank != null && ` (exon ${data.exon_rank})`}
          </span>
        )}
      </div>

      {/* ── FASTA not available message ── */}
      {!data.fasta_available && (
        <p className="text-[10px] text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded px-2 py-1">
          FASTA GRCh38 non disponible — séquences non extraites (tailles calculées depuis coordonnées).
        </p>
      )}

      {/* ── Donor site ── */}
      {data.donor_seq && (
        <div className="space-y-0.5">
          <SeqDisplay
            seq={data.donor_seq}
            hlStart={3}
            hlEnd={5}
            label={`Site donneur 5'SS${data.donor_is_gt === false ? " ⚠ non-GT" : ""}`}
          />
        </div>
      )}

      {/* ── Acceptor site ── */}
      {data.acceptor_seq && (
        <SeqDisplay
          seq={data.acceptor_seq}
          hlStart={17}
          hlEnd={19}
          label={`Site accepteur 3'SS${data.acceptor_is_ag === false ? " ⚠ non-AG" : ""}`}
        />
      )}

      {/* ── PPT ── */}
      {data.ppt_seq && (
        <PPTDisplay seq={data.ppt_seq} score={data.ppt_score} />
      )}

      {/* ── Branch-point ── */}
      {data.ppt_seq && (
        <div className="flex items-center gap-2">
          <span
            className={`w-2 h-2 rounded-full shrink-0 ${data.bp_motif_found ? "bg-green-500" : "bg-muted-foreground/40"}`}
          />
          <span className="text-[10px] text-muted-foreground">
            {data.bp_motif_found
              ? `YNYURAY trouvé (score ${data.bp_score}/7, dist. ~${data.bp_distance} nt du 3'SS)`
              : "Motif YNYURAY non détecté"}
          </span>
        </div>
      )}

      {/* ── SpliceAI placeholder ── */}
      <div className="flex items-center gap-2 px-2 py-1.5 rounded border border-dashed border-border bg-muted/20">
        <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
          SpliceAI
        </span>
        <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-muted text-[9px] text-muted-foreground border border-border">
          à venir
        </span>
        <span className="text-[10px] text-muted-foreground">
          Score d&apos;impact sur les sites donneur / accepteur (Jaganathan et al. 2019)
        </span>
      </div>
    </div>
  );
}
