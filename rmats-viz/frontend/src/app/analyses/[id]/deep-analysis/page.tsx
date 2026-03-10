"use client";

/**
 * DeepAnalysisListPage
 * =====================
 * Lists saved deep analyses for an analysis.
 * Allows creating a new deep analysis with threshold parameters.
 *
 * Route: /analyses/[id]/deep-analysis
 */

import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getAnalysis } from "@/lib/api";
import {
  listDeepAnalyses,
  createDeepAnalysis,
  deleteDeepAnalysis,
  listEvents,
} from "@/lib/api";
import type { DeepAnalysisCreate } from "@/lib/api/deep-analyses";
import { useT } from "@/contexts/LanguageContext";
import type { GeneEntry } from "@/types/gene";

// Available deep-analysis modules
const MODULES = [
  { key: "splice", label: "Splice site analysis" },
  { key: "motifs", label: "Motif patterns (PWM)" },
  { key: "permutation", label: "Permutation test" },
  { key: "frame", label: "Reading frame analysis" },
] as const;

export default function DeepAnalysisListPage() {
  const { id } = useParams<{ id: string }>();
  const t = useT();
  const qc = useQueryClient();

  // Analysis metadata
  const { data: analysis } = useQuery({
    queryKey: ["analysis", id],
    queryFn: () => getAnalysis(id),
  });

  // Saved deep analyses
  const { data: deepAnalyses = [], isLoading } = useQuery({
    queryKey: ["deep-analyses", id],
    queryFn: () => listDeepAnalyses(id),
    enabled: !!id,
  });

  // Form state for new deep analysis
  const [showForm, setShowForm] = useState(false);
  const [fdrThreshold, setFdrThreshold] = useState(0.05);
  const [deltaPsiMin, setDeltaPsiMin] = useState(0.1);
  const [pvalThreshold, setPvalThreshold] = useState<number | null>(null);
  const [selectedModules, setSelectedModules] = useState<Set<string>>(
    new Set(["splice", "permutation", "frame"])
  );
  const [name, setName] = useState("");

  // Preview: count how many events match the thresholds
  const { data: previewPage } = useQuery({
    queryKey: ["events-preview", id, fdrThreshold, deltaPsiMin, pvalThreshold],
    queryFn: () =>
      listEvents(id, {
        fdr_max: fdrThreshold,
        delta_psi_min: deltaPsiMin,
        p_value_max: pvalThreshold ?? undefined,
        page: 1,
        page_size: 1,
      }),
    enabled: !!id && showForm,
  });

  // Total events for non-significant count
  const { data: totalPage } = useQuery({
    queryKey: ["events-total", id],
    queryFn: () => listEvents(id, { page: 1, page_size: 1 }),
    enabled: !!id && showForm,
  });

  const nSignificant = previewPage?.total ?? 0;
  const nTotal = totalPage?.total ?? 0;
  const nNotSignificant = nTotal - nSignificant;

  const createMutation = useMutation({
    mutationFn: (body: DeepAnalysisCreate) => createDeepAnalysis(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["deep-analyses", id] });
      setShowForm(false);
      setName("");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (deepId: string) => deleteDeepAnalysis(deepId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["deep-analyses", id] });
    },
  });

  const handleCreate = () => {
    createMutation.mutate({
      name: name || undefined,
      fdr_threshold: fdrThreshold,
      pvalue_threshold: pvalThreshold ?? undefined,
      delta_psi_min: deltaPsiMin,
      modules: Array.from(selectedModules),
    });
  };

  const toggleModule = (key: string) => {
    setSelectedModules((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const mutatedGenes = useMemo<GeneEntry[]>(
    () =>
      (analysis?.mutated_genes ?? []).filter(
        (g): g is GeneEntry => typeof g === "object" && "ensembl_id" in g,
      ),
    [analysis],
  );

  const group1 = analysis?.sample_groups.find((g) => g.group_index === 1);
  const group2 = analysis?.sample_groups.find((g) => g.group_index === 2);

  return (
    <div className="space-y-6 max-w-4xl">
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
        <span className="text-foreground font-medium">{t("deepAnalysis.breadcrumb")}</span>
      </nav>

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-foreground">
            {t("deepAnalysis.title")}
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
          onClick={() => setShowForm((v) => !v)}
          className="inline-flex items-center gap-1.5 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-semibold transition-colors shadow-sm shrink-0"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          {t("deepAnalysis.newAnalysis")}
        </button>
      </div>

      {/* Back link */}
      <Link
        href={`/analyses/${id}`}
        className="inline-flex items-center gap-1.5 text-sm text-blue-600 dark:text-blue-400 hover:underline"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        {t("deepAnalysis.backToEvents")}
      </Link>

      {/* New deep analysis form */}
      {showForm && (
        <div className="rounded-xl border border-blue-200 dark:border-blue-800 bg-blue-50/50 dark:bg-blue-950/20 p-5 space-y-4">
          <h2 className="text-sm font-bold text-foreground">
            {t("deepAnalysis.newAnalysisForm")}
          </h2>

          {/* Name */}
          <div>
            <label className="text-xs font-medium text-muted-foreground">{t("deepAnalysis.formName")}</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("deepAnalysis.formNamePlaceholder")}
              className="mt-1 w-full border border-border rounded-lg px-3 py-2 text-sm bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Threshold inputs */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="text-xs font-medium text-muted-foreground">FDR max</label>
              <input
                type="number"
                step="0.01"
                min="0"
                max="1"
                value={fdrThreshold}
                onChange={(e) => setFdrThreshold(Number(e.target.value))}
                className="mt-1 w-full border border-border rounded-lg px-3 py-2 text-sm bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500 tabular-nums"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground">|ΔPSI| min</label>
              <input
                type="number"
                step="0.01"
                min="0"
                max="1"
                value={deltaPsiMin}
                onChange={(e) => setDeltaPsiMin(Number(e.target.value))}
                className="mt-1 w-full border border-border rounded-lg px-3 py-2 text-sm bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500 tabular-nums"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground">p-value max ({t("deepAnalysis.optional")})</label>
              <input
                type="number"
                step="0.01"
                min="0"
                max="1"
                value={pvalThreshold ?? ""}
                onChange={(e) => setPvalThreshold(e.target.value ? Number(e.target.value) : null)}
                placeholder="—"
                className="mt-1 w-full border border-border rounded-lg px-3 py-2 text-sm bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500 tabular-nums"
              />
            </div>
          </div>

          {/* Preview counts */}
          <div className="flex items-center gap-4 text-sm">
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-950/30 text-green-700 dark:text-green-300 font-medium">
              {nSignificant} {t("deepAnalysis.significant")}
            </span>
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/30 text-slate-600 dark:text-slate-400 font-medium">
              {nNotSignificant > 0 ? nNotSignificant : "—"} {t("deepAnalysis.notSignificant")}
            </span>
          </div>

          {/* Modules */}
          <div>
            <label className="text-xs font-medium text-muted-foreground">{t("deepAnalysis.modules")}</label>
            <div className="flex flex-wrap gap-2 mt-2">
              {MODULES.map(({ key, label }) => (
                <button
                  key={key}
                  onClick={() => toggleModule(key)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                    selectedModules.has(key)
                      ? "bg-blue-600 text-white border-blue-600"
                      : "border-border text-muted-foreground hover:text-foreground hover:bg-muted"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Submit */}
          <div className="flex items-center gap-3">
            <button
              onClick={handleCreate}
              disabled={createMutation.isPending || nSignificant === 0}
              className="inline-flex items-center gap-1.5 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-semibold transition-colors disabled:opacity-50"
            >
              {createMutation.isPending ? t("deepAnalysis.creating") : t("deepAnalysis.create")}
            </button>
            <button
              onClick={() => setShowForm(false)}
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              {t("deepAnalysis.cancel")}
            </button>
          </div>
        </div>
      )}

      {/* Saved deep analyses list */}
      {isLoading && (
        <div className="flex items-center gap-2 text-muted-foreground text-sm py-6">
          <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          {t("deepAnalysis.loading")}
        </div>
      )}

      {!isLoading && deepAnalyses.length === 0 && !showForm && (
        <div className="text-center py-12 text-muted-foreground">
          <p className="text-sm">{t("deepAnalysis.noSavedAnalyses")}</p>
          <p className="text-xs mt-2">{t("deepAnalysis.noSavedAnalysesHint")}</p>
        </div>
      )}

      {deepAnalyses.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-bold text-foreground">{t("deepAnalysis.savedAnalyses")}</h2>
          {deepAnalyses.map((da) => (
            <div
              key={da.id}
              className="flex items-center justify-between gap-4 border border-border rounded-xl bg-card p-4 shadow-sm hover:shadow-md transition-shadow"
            >
              <Link
                href={`/analyses/${id}/deep-analysis/${da.id}`}
                className="flex-1 min-w-0"
              >
                <div className="flex items-center gap-3">
                  <span className="text-sm font-semibold text-foreground truncate">{da.name}</span>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                    da.status === "ready"
                      ? "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300"
                      : da.status === "computing"
                      ? "bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300"
                      : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400"
                  }`}>
                    {da.status}
                  </span>
                </div>
                <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                  <span>FDR ≤ {da.fdr_threshold}</span>
                  <span>|ΔPSI| ≥ {da.delta_psi_min}</span>
                  <span className="text-green-600 dark:text-green-400 font-medium">{da.n_significant} sig.</span>
                  <span>{da.n_not_significant} non-sig.</span>
                  <span>{new Date(da.created_at).toLocaleDateString()}</span>
                </div>
              </Link>
              <button
                onClick={() => {
                  if (confirm(t("deepAnalysis.confirmDelete")))
                    deleteMutation.mutate(da.id);
                }}
                disabled={deleteMutation.isPending}
                className="text-muted-foreground hover:text-destructive transition-colors shrink-0"
                title={t("deepAnalysis.delete")}
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          ))}
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
