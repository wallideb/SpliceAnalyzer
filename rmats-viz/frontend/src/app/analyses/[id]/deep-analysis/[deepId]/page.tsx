"use client";

/**
 * DeepAnalysisDetailPage
 * =======================
 * Displays a saved deep analysis with its significant/non-significant events.
 * Reuses existing Top10View and PermutationPanel components.
 *
 * Route: /analyses/[id]/deep-analysis/[deepId]
 */

import { useState, useCallback, useMemo, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getAnalysis, downloadAnalysisPDF } from "@/lib/api";
import { getDeepAnalysis, getDeepAnalysisEvents } from "@/lib/api/deep-analyses";
import { computeSpliceFeatures } from "@/lib/api/splice";
import { useT } from "@/contexts/LanguageContext";
import { Top10View } from "@/components/events/Top10View";
import { MutatedGenePanel } from "@/components/top10/MutatedGenePanel";
import { PermutationPanel } from "@/components/top10/PermutationPanel";
import { PatternComparisonPanel } from "@/components/deep-analysis/PatternComparisonPanel";
import type { GeneEntry } from "@/types/gene";

export default function DeepAnalysisDetailPage() {
  const { id, deepId } = useParams<{ id: string; deepId: string }>();
  const t = useT();
  const qc = useQueryClient();

  const { data: analysis } = useQuery({
    queryKey: ["analysis", id],
    queryFn: () => getAnalysis(id),
  });

  const { data: deepAnalysis } = useQuery({
    queryKey: ["deep-analysis", deepId],
    queryFn: () => getDeepAnalysis(deepId),
    enabled: !!deepId,
  });

  const { data: significantEvents = [], isLoading: loadingSig } = useQuery({
    queryKey: ["deep-analysis-events", deepId, true],
    queryFn: () => getDeepAnalysisEvents(deepId, true),
    enabled: !!deepId,
  });

  const activeModules = useMemo<Set<string>>(
    () => new Set(deepAnalysis?.modules ?? []),
    [deepAnalysis],
  );

  const mutatedGenes = useMemo<GeneEntry[]>(
    () =>
      (analysis?.mutated_genes ?? []).filter(
        (g): g is GeneEntry => typeof g === "object" && "ensembl_id" in g,
      ),
    [analysis],
  );

  // Auto-compute splice features if splice module active
  const { mutate: autoCompute } = useMutation({
    mutationFn: () => computeSpliceFeatures(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["splice-feature"] }),
  });
  useEffect(() => {
    if (activeModules.has("splice") && id) autoCompute();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const group1 = analysis?.sample_groups.find((g) => g.group_index === 1);
  const group2 = analysis?.sample_groups.find((g) => g.group_index === 2);

  const [isExportingPDF, setIsExportingPDF] = useState(false);
  const handleExportPDF = useCallback(async () => {
    setIsExportingPDF(true);
    try {
      await downloadAnalysisPDF(id);
    } catch {
      alert(t("analysisDetail.pdfError"));
    } finally {
      setIsExportingPDF(false);
    }
  }, [id, t]);

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-1 text-sm text-muted-foreground flex-wrap">
        <Link href="/analyses" className="hover:text-foreground transition-colors inline-flex items-center gap-1">
          <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 22V12h6v10" />
          </svg>
          Analyses
        </Link>
        <ChevronIcon />
        <Link href={`/analyses/${id}`} className="hover:text-foreground transition-colors truncate max-w-[180px]">
          {analysis?.name ?? "..."}
        </Link>
        <ChevronIcon />
        <Link href={`/analyses/${id}/deep-analysis`} className="hover:text-foreground transition-colors">
          {t("deepAnalysis.breadcrumb")}
        </Link>
        <ChevronIcon />
        <span className="text-foreground font-medium truncate max-w-[200px]">
          {deepAnalysis?.name ?? "..."}
        </span>
      </nav>

      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-foreground">
            {deepAnalysis?.name ?? "..."}
          </h1>
          {group1 && group2 && (
            <p className="text-sm text-muted-foreground mt-1">
              <span className="text-red-500 dark:text-red-400 font-semibold">{group1.group_label}</span>
              {" vs "}
              <span className="text-blue-500 dark:text-blue-400 font-semibold">{group2.group_label}</span>
            </p>
          )}
        </div>
        <button
          onClick={handleExportPDF}
          disabled={isExportingPDF}
          className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-semibold bg-rose-600 hover:bg-rose-700 text-white rounded-lg disabled:opacity-50 transition-colors shrink-0"
        >
          {isExportingPDF ? (
            <svg className="animate-spin w-3.5 h-3.5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          ) : (
            <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          )}
          {isExportingPDF ? "PDF..." : t("analysisDetail.pdf")}
        </button>
      </div>

      {/* Methodology bar */}
      {deepAnalysis && (
        <div className="flex flex-wrap items-center gap-3 p-3 rounded-xl border border-border bg-muted/40 text-xs">
          <span className="font-semibold text-foreground">{t("deepAnalysis.methodology")}</span>
          <span className="px-2 py-0.5 rounded bg-card border border-border">FDR ≤ {deepAnalysis.fdr_threshold}</span>
          <span className="px-2 py-0.5 rounded bg-card border border-border">|ΔPSI| ≥ {deepAnalysis.delta_psi_min}</span>
          {deepAnalysis.pvalue_threshold != null && (
            <span className="px-2 py-0.5 rounded bg-card border border-border">p ≤ {deepAnalysis.pvalue_threshold}</span>
          )}
          <span className="text-green-600 dark:text-green-400 font-medium">{deepAnalysis.n_significant} {t("deepAnalysis.significant")}</span>
          <span className="text-muted-foreground">{deepAnalysis.n_not_significant} {t("deepAnalysis.notSignificant")}</span>
          <span className="text-muted-foreground">{new Date(deepAnalysis.created_at).toLocaleDateString()}</span>
          {deepAnalysis.modules.length > 0 && (
            <span className="text-muted-foreground">
              {t("deepAnalysis.modules")}: {deepAnalysis.modules.join(", ")}
            </span>
          )}
        </div>
      )}

      {/* Back link */}
      <Link
        href={`/analyses/${id}/deep-analysis`}
        className="inline-flex items-center gap-1.5 text-sm text-blue-600 dark:text-blue-400 hover:underline"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        {t("deepAnalysis.backToList")}
      </Link>

      {/* Mutated gene panel */}
      <MutatedGenePanel mutatedGenes={mutatedGenes} analysisId={id} />

      {/* Loading */}
      {loadingSig && (
        <div className="flex items-center gap-2 text-muted-foreground text-sm py-6">
          <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          {t("deepAnalysis.loading")}
        </div>
      )}

      {/* Significant events view */}
      {!loadingSig && significantEvents.length > 0 && (
        <Top10View
          events={significantEvents}
          mutatedGenes={mutatedGenes}
          activeModules={activeModules}
          analysisId={id}
          group1Label={group1?.group_label ?? "Group 1"}
          group2Label={group2?.group_label ?? "Group 2"}
          deepAnalysisId={deepId}
          fdrThreshold={deepAnalysis?.fdr_threshold}
          deltaPsiMin={deepAnalysis?.delta_psi_min}
        />
      )}

      {!loadingSig && significantEvents.length === 0 && (
        <p className="text-sm text-muted-foreground py-6 text-center">
          {t("deepAnalysis.noEvents")}
        </p>
      )}

      {/* Pattern comparison panel */}
      {(activeModules.has("splice") || activeModules.has("frame")) && (
        <div className="space-y-3">
          <h2 className="text-sm font-bold text-foreground">
            Pattern comparison: significant vs non-significant
          </h2>
          <PatternComparisonPanel deepId={deepId} />
        </div>
      )}

      {/* Permutation panel */}
      {activeModules.has("permutation") && (
        <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
          <h2 className="text-sm font-bold text-foreground mb-4">
            {t("deepAnalysis.permutationTitle")}
          </h2>
          <PermutationPanel analysisId={id} />
        </div>
      )}
    </div>
  );
}

function ChevronIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3 text-muted-foreground/50" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
    </svg>
  );
}
