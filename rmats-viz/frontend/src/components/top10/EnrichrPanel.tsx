"use client";

/**
 * EnrichrPanel
 * =============
 * Displays Enrichr gene-set enrichment results for significant events.
 * Queries: GET /api/v1/deep-analyses/{id}/enrichr
 */

import { useQuery } from "@tanstack/react-query";
import { useState, useMemo } from "react";
import { fetchJSON, BASE } from "@/lib/api/client";
import { ScienceNote } from "@/components/ScienceNote";
import { useT } from "@/contexts/LanguageContext";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface EnrichrTermItem {
  library: string;
  rank: number;
  term: string;
  p_value: number;
  adjusted_p_value: number;
  z_score: number;
  combined_score: number;
  overlap: string;
  genes: string[];
}

interface EnrichrResponse {
  n_genes_submitted: number;
  terms: EnrichrTermItem[];
  error: string | null;
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

function getEnrichrResults(deepId: string): Promise<EnrichrResponse> {
  return fetchJSON(`${BASE}/deep-analyses/${deepId}/enrichr`);
}

// ---------------------------------------------------------------------------
// Library display names
// ---------------------------------------------------------------------------

const LIB_LABELS: Record<string, string> = {
  KEGG_2021_Human: "KEGG 2021",
  GO_Biological_Process_2023: "GO Biological Process",
  GO_Molecular_Function_2023: "GO Molecular Function",
  Reactome_2022: "Reactome 2022",
  WikiPathway_2023_Human: "WikiPathways 2023",
};

const LIB_COLORS: Record<string, string> = {
  KEGG_2021_Human: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300 border-blue-200 dark:border-blue-800",
  GO_Biological_Process_2023: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300 border-green-200 dark:border-green-800",
  GO_Molecular_Function_2023: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800",
  Reactome_2022: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300 border-purple-200 dark:border-purple-800",
  WikiPathway_2023_Human: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300 border-amber-200 dark:border-amber-800",
};

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface EnrichrPanelProps {
  deepAnalysisId: string;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function EnrichrPanel({ deepAnalysisId }: EnrichrPanelProps) {
  const t = useT();
  const [selectedLib, setSelectedLib] = useState<string | null>(null);
  const [expandedTerm, setExpandedTerm] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["enrichr", deepAnalysisId],
    queryFn: () => getEnrichrResults(deepAnalysisId),
    enabled: !!deepAnalysisId,
    staleTime: 10 * 60 * 1000,
  });

  // Available libraries
  const libraries = useMemo(() => {
    if (!data) return [];
    return [...new Set(data.terms.map((t) => t.library))];
  }, [data]);

  // Filtered terms
  const filteredTerms = useMemo(() => {
    if (!data) return [];
    let terms = data.terms;
    if (selectedLib) {
      terms = terms.filter((t) => t.library === selectedLib);
    }
    return terms;
  }, [data, selectedLib]);

  // ── Loading ──
  if (isLoading) {
    return (
      <div className="space-y-3 p-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-6 rounded bg-muted animate-pulse" />
        ))}
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex flex-col items-center gap-3 py-8 text-center">
        <p className="text-sm text-muted-foreground">{t("enrichrPanel.error")}</p>
      </div>
    );
  }

  if (data.error && data.terms.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 py-8 text-center">
        <svg xmlns="http://www.w3.org/2000/svg" className="w-8 h-8 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
        </svg>
        <p className="text-sm text-muted-foreground">{data.error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-5 text-xs">
      {/* Summary */}
      <div className="flex flex-wrap gap-3">
        <div className="text-center px-3 py-2 rounded-lg bg-muted/40 border border-border">
          <p className="text-[9px] text-muted-foreground uppercase tracking-wide font-semibold">{t("enrichrPanel.genesSubmitted")}</p>
          <p className="text-base font-bold text-foreground tabular-nums">{data.n_genes_submitted}</p>
        </div>
        <div className="text-center px-3 py-2 rounded-lg bg-muted/40 border border-border">
          <p className="text-[9px] text-muted-foreground uppercase tracking-wide font-semibold">{t("enrichrPanel.termsFound")}</p>
          <p className="text-base font-bold text-foreground tabular-nums">{data.terms.length}</p>
        </div>
        <div className="text-center px-3 py-2 rounded-lg bg-muted/40 border border-border">
          <p className="text-[9px] text-muted-foreground uppercase tracking-wide font-semibold">{t("enrichrPanel.libraries")}</p>
          <p className="text-base font-bold text-foreground tabular-nums">{libraries.length}</p>
        </div>
      </div>

      {/* Library filter */}
      <div className="flex flex-wrap gap-1.5">
        <button
          onClick={() => setSelectedLib(null)}
          className={`px-2.5 py-1 text-[10px] font-semibold rounded-full border transition-colors ${
            selectedLib === null
              ? "bg-blue-600 border-blue-600 text-white"
              : "bg-card border-border text-muted-foreground hover:bg-muted"
          }`}
        >
          {t("enrichrPanel.allLibraries")}
        </button>
        {libraries.map((lib) => (
          <button
            key={lib}
            onClick={() => setSelectedLib(lib === selectedLib ? null : lib)}
            className={`px-2.5 py-1 text-[10px] font-semibold rounded-full border transition-colors ${
              selectedLib === lib
                ? "bg-blue-600 border-blue-600 text-white"
                : `${LIB_COLORS[lib] ?? "bg-card border-border text-muted-foreground"} hover:opacity-80`
            }`}
          >
            {LIB_LABELS[lib] ?? lib}
          </button>
        ))}
      </div>

      {/* Results */}
      {filteredTerms.length === 0 ? (
        <p className="text-sm text-muted-foreground text-center py-4">{t("enrichrPanel.noTerms")}</p>
      ) : (
        <div className="space-y-2">
          {filteredTerms.map((term, i) => {
            const isExpanded = expandedTerm === `${term.library}-${term.term}`;
            const maxScore = Math.max(...filteredTerms.map((t) => t.combined_score), 1);
            const barWidth = (term.combined_score / maxScore) * 100;
            return (
              <div
                key={`${term.library}-${term.term}-${i}`}
                className="rounded-lg border border-border bg-card overflow-hidden hover:shadow-sm transition-shadow"
              >
                <button
                  className="w-full text-left px-3 py-2 flex items-start gap-2"
                  onClick={() => setExpandedTerm(isExpanded ? null : `${term.library}-${term.term}`)}
                >
                  <span className="text-[10px] font-bold text-muted-foreground tabular-nums w-5 shrink-0 pt-0.5">
                    {term.rank}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className={`inline-flex px-1.5 py-0 rounded text-[8px] font-semibold border ${LIB_COLORS[term.library] ?? "bg-muted text-muted-foreground border-border"}`}>
                        {LIB_LABELS[term.library] ?? term.library}
                      </span>
                    </div>
                    <p className="text-xs font-semibold text-foreground truncate">{term.term}</p>
                    {/* Combined score bar */}
                    <div className="mt-1 flex items-center gap-2">
                      <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                        <div
                          className="h-full rounded-full bg-blue-500"
                          style={{ width: `${Math.min(100, barWidth)}%` }}
                        />
                      </div>
                      <span className="text-[9px] text-muted-foreground tabular-nums shrink-0">
                        {term.combined_score.toFixed(1)}
                      </span>
                    </div>
                  </div>
                  <div className="text-right shrink-0 pt-0.5">
                    <p className={`text-[10px] font-semibold tabular-nums ${
                      term.adjusted_p_value < 0.01 ? "text-green-600 dark:text-green-400" :
                      term.adjusted_p_value < 0.05 ? "text-amber-600 dark:text-amber-400" :
                      "text-muted-foreground"
                    }`}>
                      {term.adjusted_p_value < 0.0001 ? term.adjusted_p_value.toExponential(2) : term.adjusted_p_value.toFixed(4)}
                    </p>
                    <p className="text-[9px] text-muted-foreground">{term.overlap}</p>
                  </div>
                </button>

                {/* Expanded: show genes */}
                {isExpanded && term.genes.length > 0 && (
                  <div className="px-3 pb-2 pt-0">
                    <div className="flex flex-wrap gap-1 mt-1">
                      {term.genes.map((g) => (
                        <span
                          key={g}
                          className="inline-flex px-1.5 py-0.5 rounded text-[9px] font-medium bg-muted border border-border text-foreground"
                        >
                          {g}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {data.error && (
        <div className="rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/20 p-3 text-[11px] text-amber-700 dark:text-amber-300">
          {data.error}
        </div>
      )}

      <ScienceNote
        title={t("scienceNotes.enrichr.title")}
        body={t("scienceNotes.enrichr.body")}
        refs={["enrichr"]}
      />
    </div>
  );
}
