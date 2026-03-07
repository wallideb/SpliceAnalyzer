"use client";

/**
 * DeepAnalysisPage
 * =================
 * Analyse approfondie d'une sélection d'événements d'épissage.
 *
 * Contient toujours :
 *   • Les Top 10 événements de l'analyse (classés par FDR + |ΔPSI|)
 *   • Les événements du panier pour cette analyse
 *
 * Les modules optionnels (stringdb, pathways, motifs, splice) sont lus
 * depuis le paramètre URL ?modules=stringdb,pathways et contrôlent les
 * onglets supplémentaires dans la sidebar.
 *
 * Route : /analyses/[id]/deep-analysis?modules=stringdb,pathways,...
 */

import { useMemo, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { getAnalysis, getTop10 } from "@/lib/api";
import { computeSpliceFeatures } from "@/lib/api/splice";
import { useBasket } from "@/contexts/BasketContext";
import { Top10View } from "@/components/events/Top10View";
import { MutatedGenePanel } from "@/components/top10/MutatedGenePanel";
import { PermutationPanel } from "@/components/top10/PermutationPanel";
import type { GeneEntry } from "@/types/gene";
import type { SplicingEvent } from "@/types/event";

export default function DeepAnalysisPage() {
  const { id } = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const { items: basketItems } = useBasket();

  // Parse selected optional modules from URL
  const activeModules = useMemo<Set<string>>(() => {
    const raw = searchParams.get("modules") ?? "";
    return new Set(raw.split(",").filter(Boolean));
  }, [searchParams]);

  // Analysis metadata
  const { data: analysis } = useQuery({
    queryKey: ["analysis", id],
    queryFn: () => getAnalysis(id),
  });

  // Top-10 events (always included)
  const { data: top10 = [], isLoading: loadingTop10 } = useQuery({
    queryKey: ["top10", id],
    queryFn: () => getTop10(id),
    enabled: !!id,
  });

  // Basket events for this analysis (excluding those already in top10)
  const basketForAnalysis = useMemo<SplicingEvent[]>(() => {
    const top10Ids = new Set((top10 as SplicingEvent[]).map((e) => e.id));
    return basketItems
      .filter((item) => item.analysisId === id && !top10Ids.has(item.event.id))
      .map((item) => item.event);
  }, [basketItems, id, top10]);

  // Merged event list: top10 first, then basket-only events
  const allEvents = useMemo<SplicingEvent[]>(
    () => [...(top10 as SplicingEvent[]), ...basketForAnalysis],
    [top10, basketForAnalysis],
  );

  // Resolve mutated gene entries (guard against legacy string format)
  const mutatedGenes = useMemo<GeneEntry[]>(
    () =>
      (analysis?.mutated_genes ?? []).filter(
        (g): g is GeneEntry => typeof g === "object" && "ensembl_id" in g,
      ),
    [analysis],
  );

  // Auto-compute splice features when the "splice" module is active.
  // Fires once on mount (or when id changes) so per-event views are ready
  // before the user switches to the "Sites consensus" tab.
  const qc = useQueryClient();
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
  const basketCount = basketForAnalysis.length;

  return (
    <div className="space-y-6">
      {/* ── Breadcrumb & Header ── */}
      <div>
        <nav className="flex items-center gap-1 text-sm text-muted-foreground mb-2 flex-wrap">
          <Link
            href="/analyses"
            className="hover:text-foreground transition-colors inline-flex items-center gap-1"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="w-3.5 h-3.5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"
              />
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M9 22V12h6v10"
              />
            </svg>
            Analyses
          </Link>
          <ChevronIcon />
          <Link
            href={`/analyses/${id}`}
            className="hover:text-foreground transition-colors truncate max-w-[180px]"
          >
            {analysis?.name ?? "…"}
          </Link>
          <ChevronIcon />
          <span className="text-foreground font-medium">
            Analyse approfondie
          </span>
        </nav>

        <h1 className="text-2xl font-extrabold tracking-tight text-foreground">
          Analyse approfondie
        </h1>

        {group1 && group2 && (
          <p className="text-sm text-muted-foreground mt-1">
            <span className="text-red-500 dark:text-red-400 font-semibold">
              {group1.group_label}
            </span>
            {" vs "}
            <span className="text-blue-500 dark:text-blue-400 font-semibold">
              {group2.group_label}
            </span>
          </p>
        )}
      </div>

      {/* ── Back link ── */}
      <Link
        href={`/analyses/${id}`}
        className="inline-flex items-center gap-1.5 text-sm text-blue-600 dark:text-blue-400 hover:underline"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="w-3.5 h-3.5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2.5}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
        Retour aux événements
      </Link>

      {/* ── Selection summary ── */}
      <div className="flex flex-wrap gap-3">
        {/* Top-10 badge */}
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/30 text-xs">
          <span className="w-5 h-5 flex items-center justify-center rounded-full bg-blue-600 text-white font-bold text-[10px]">
            10
          </span>
          <span className="text-blue-700 dark:text-blue-300 font-medium">
            Top 10 toujours inclus
          </span>
        </div>

        {/* Basket events badge */}
        {basketCount > 0 && (
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-violet-200 dark:border-violet-800 bg-violet-50 dark:bg-violet-950/30 text-xs">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="w-4 h-4 text-violet-600 dark:text-violet-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13l-1.4 7h12.8M9 21a1 1 0 100-2 1 1 0 000 2zm10 0a1 1 0 100-2 1 1 0 000 2z"
              />
            </svg>
            <span className="text-violet-700 dark:text-violet-300 font-medium">
              +{basketCount} du panier
            </span>
          </div>
        )}

        {/* Active optional modules */}
        {activeModules.size > 0 && (
          <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-muted/40 text-xs text-muted-foreground">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="w-3.5 h-3.5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4"
              />
            </svg>
            {activeModules.size} module
            {activeModules.size > 1 ? "s" : ""} optionnel
            {activeModules.size > 1 ? "s" : ""} activé
            {activeModules.size > 1 ? "s" : ""}
          </div>
        )}
      </div>

      {/* ── Mutated gene annotation panel ── */}
      <MutatedGenePanel mutatedGenes={mutatedGenes} analysisId={id} />

      {/* ── Loading state ── */}
      {loadingTop10 && (
        <div className="flex items-center gap-2 text-muted-foreground text-sm py-6">
          <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          Chargement des événements…
        </div>
      )}

      {/* ── Main annotated view ── */}
      {!loadingTop10 && allEvents.length > 0 && (
        <Top10View
          events={allEvents}
          mutatedGenes={mutatedGenes}
          activeModules={activeModules}
          analysisId={id}
          group1Label={group1?.group_label ?? "Groupe 1"}
          group2Label={group2?.group_label ?? "Groupe 2"}
        />
      )}

      {!loadingTop10 && allEvents.length === 0 && (
        <p className="text-sm text-muted-foreground py-6 text-center">
          Aucun événement à afficher. Ajoutez des événements au panier ou
          vérifiez que l&apos;analyse a des données.
        </p>
      )}

      {/* ── 4B — Test de permutation — Significativité ── */}
      <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
        <h2 className="text-sm font-bold text-foreground mb-4">
          Significativité par permutation
        </h2>
        <PermutationPanel analysisId={id} />
      </div>
    </div>
  );
}

function ChevronIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className="w-3 h-3 text-muted-foreground/50"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
    </svg>
  );
}
