"use client";

/**
 * SpliceView — per-card splice signal view (mode "splice")
 * =========================================================
 * Affiche uniquement l'ExonDiagram plein format avec toutes les données
 * encodées dans les tooltips SVG interactifs. Les sections texte ont été
 * supprimées — toutes les informations sont accessibles via les zones hover.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getEventSpliceFeature, computeSpliceFeatures } from "@/lib/api/splice";
import { ScienceNote } from "@/components/ScienceNote";
import { useT } from "@/contexts/LanguageContext";
import type { SplicingEvent } from "@/types/event";
import { ExonDiagram } from "./ExonDiagram";
import { SpliceSiteTrack } from "./SpliceSiteTrack";
import { PPTTrack } from "./PPTTrack";
import { MANETranscriptTrack } from "./MANETranscriptTrack";

// ---------------------------------------------------------------------------
// Helper — mean of a comma-separated PSI string
// ---------------------------------------------------------------------------

function meanPsi(s: string | null | undefined): number | null {
  if (!s) return null;
  const vals = s.split(",").map(Number).filter((v) => !isNaN(v) && isFinite(v));
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function SpliceView({
  event: ev,
  analysisId,
}: {
  event: SplicingEvent;
  analysisId?: string;
}) {
  const t = useT();
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

  return (
    <div className="space-y-0">
      <ExonDiagram
        exonSize={data.exon_size}
        upstreamIntronSize={data.upstream_intron_size}
        downstreamIntronSize={data.downstream_intron_size}
        incLevelDifference={ev.inc_level_difference ?? null}
        fdr={ev.fdr ?? null}
        pValue={ev.p_value ?? null}
        strand={ev.strand ?? null}
        donorIsGt={data.donor_is_gt}
        acceptorIsAg={data.acceptor_is_ag}
        psi1={meanPsi(ev.inc_level_1)}
        psi2={meanPsi(ev.inc_level_2)}
        exonStart={ev.exon_start ?? null}
        exonEnd={ev.exon_end ?? null}
        upstreamExonStart={ev.upstream_es ?? null}
        upstreamExonEnd={ev.upstream_ee ?? null}
        downstreamExonStart={ev.downstream_es ?? null}
        downstreamExonEnd={ev.downstream_ee ?? null}
        frameClass={data.frame_class ?? null}
        maneTranscriptId={data.mane_transcript_id ?? null}
        exonRank={data.exon_rank ?? null}
        donorSeq={data.donor_seq ?? null}
        acceptorSeq={data.acceptor_seq ?? null}
        pptScore={data.ppt_score ?? null}
        pptSeq={data.ppt_seq ?? null}
        bpFound={data.bp_motif_found ?? null}
        bpDistance={data.bp_distance ?? null}
      />

      {/* 1C — MANE transcript linear diagram */}
      <MANETranscriptTrack
        eventId={ev.id}
        maneTranscriptId={data.mane_transcript_id ?? null}
        exonRank={data.exon_rank ?? null}
      />

      {/* 1B — Splice-site sequence tracks with position axes */}
      {(data.donor_seq || data.acceptor_seq) && (
        <SpliceSiteTrack
          donorSeq={data.donor_seq ?? null}
          acceptorSeq={data.acceptor_seq ?? null}
        />
      )}

      {/* 1D — PPT per-nucleotide track */}
      {data.ppt_seq && (
        <PPTTrack
          pptSeq={data.ppt_seq}
          pptScore={data.ppt_score ?? null}
          pptLongestRun={data.ppt_longest_run ?? null}
          bpFound={data.bp_motif_found ?? null}
          bpDistance={data.bp_distance ?? null}
        />
      )}

      <ScienceNote
        title={t("scienceNotes.exonDiagram.title")}
        body={t("scienceNotes.exonDiagram.body")}
        refs={["rmats", "benjamini_hochberg", "mane_select"]}
      />
    </div>
  );
}
