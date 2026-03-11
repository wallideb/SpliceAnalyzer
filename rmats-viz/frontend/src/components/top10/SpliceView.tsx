"use client";

/**
 * SpliceView — per-card splice signal view (mode "splice")
 * =========================================================
 * Affiche uniquement l'ExonDiagram plein format avec toutes les données
 * encodées dans les tooltips SVG interactifs. Les sections texte ont été
 * supprimées — toutes les informations sont accessibles via les zones hover.
 */

import { useRef, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getEventSpliceFeature, computeSpliceFeatures } from "@/lib/api/splice";
import { ScienceNote } from "@/components/ScienceNote";
import { useT } from "@/contexts/LanguageContext";
import type { SplicingEvent } from "@/types/event";
import { ExonDiagram } from "./ExonDiagram";
import { SpliceSiteTrack } from "./SpliceSiteTrack";
import { PPTTrack } from "./PPTTrack";
import { MANETranscriptTrack } from "./MANETranscriptTrack";
import { ComputeProgressBar } from "./ComputeProgressBar";
import { ZoomableContainer } from "@/components/ZoomableContainer";

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
  const diagramRef = useRef<HTMLDivElement>(null);

  const exportSVG = useCallback(() => {
    const svgEl = diagramRef.current?.querySelector("svg");
    if (!svgEl) return;
    const clone = svgEl.cloneNode(true) as SVGSVGElement;
    // Add white background for standalone viewing
    const bg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    bg.setAttribute("width", "100%");
    bg.setAttribute("height", "100%");
    bg.setAttribute("fill", "white");
    clone.insertBefore(bg, clone.firstChild);
    // Inline CSS variables as computed values
    clone.querySelectorAll("[fill],[stroke]").forEach((el) => {
      for (const attr of ["fill", "stroke"] as const) {
        const val = el.getAttribute(attr);
        if (val?.startsWith("var(") || val?.startsWith("hsl(var(")) {
          const computed = getComputedStyle(svgEl).getPropertyValue(
            val.match(/--[\w-]+/)?.[0] ?? "",
          );
          if (computed) el.setAttribute(attr, computed.trim());
        }
      }
    });
    const xml = new XMLSerializer().serializeToString(clone);
    const blob = new Blob([xml], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${ev.gene_symbol ?? ev.id}_exon_diagram.svg`;
    a.click();
    URL.revokeObjectURL(url);
  }, [ev.gene_symbol, ev.id]);

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
      <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-muted/40 border border-border text-xs text-muted-foreground">
        <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <div>
          <span className="font-semibold text-foreground">{t("spliceView.nonSeEventTitle", { type: ev.event_type })}</span>
          {" — "}{t("spliceView.nonSeEventDesc")}
        </div>
      </div>
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
          {t("spliceView.notComputed")}
        </p>
        {analysisId && compute.isSuccess && (
          <ComputeProgressBar
            analysisId={analysisId}
            onComplete={() => qc.invalidateQueries({ queryKey: ["splice-feature", ev.id] })}
          />
        )}
        {analysisId && !compute.isSuccess && (
          <button
            onClick={() => compute.mutate()}
            disabled={compute.isPending}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50 transition-colors"
          >
            {compute.isPending ? t("spliceView.computing") : t("spliceView.computeBtn")}
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-0">
      {/* Export SVG button */}
      <div className="flex justify-end mb-1">
        <button
          onClick={exportSVG}
          className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium text-muted-foreground hover:text-foreground border border-border rounded-md hover:bg-muted transition-colors"
          title="Download exon diagram as SVG"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          SVG
        </button>
      </div>
      <div ref={diagramRef}>
      <ZoomableContainer>
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
      </ZoomableContainer>
      </div>

      {/* 1C — MANE transcript linear diagram */}
      <MANETranscriptTrack
        eventId={ev.id}
        maneTranscriptId={data.mane_transcript_id ?? null}
        exonRank={data.exon_rank ?? null}
      />

      {/* 1B — Splice-site sequence tracks with position axes (always shown) */}
      <ZoomableContainer>
        <SpliceSiteTrack
          donorSeq={data.donor_seq ?? null}
          acceptorSeq={data.acceptor_seq ?? null}
          upstreamDonorSeq={data.upstream_donor_seq ?? null}
          downstreamAcceptorSeq={data.downstream_acceptor_seq ?? null}
          sequenceSource={data.sequence_source ?? null}
        />
      </ZoomableContainer>

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
