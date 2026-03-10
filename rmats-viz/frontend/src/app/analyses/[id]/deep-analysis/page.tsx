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

import { useMemo, useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { getAnalysis, getTop10 } from "@/lib/api";
import { computeSpliceFeatures } from "@/lib/api/splice";
import { useBasket } from "@/contexts/BasketContext";
import { useT } from "@/contexts/LanguageContext";
import { Top10View } from "@/components/events/Top10View";
import { MutatedGenePanel } from "@/components/top10/MutatedGenePanel";
import { PermutationPanel } from "@/components/top10/PermutationPanel";
import type { GeneEntry } from "@/types/gene";
import type { SplicingEvent } from "@/types/event";

export default function DeepAnalysisPage() {
  const { id } = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const { items: basketItems } = useBasket();
  const t = useT();

  // Parse selected optional modules from URL
  const activeModules = useMemo<Set<string>>(() => {
    const raw = searchParams.get("modules") ?? "";
    return new Set(raw.split(",").filter(Boolean));
  }, [searchParams]);

  // Top-N selector state (default 10, range 5–50)
  const [topN, setTopN] = useState(10);

  // Analysis metadata
  const { data: analysis } = useQuery({
    queryKey: ["analysis", id],
    queryFn: () => getAnalysis(id),
  });

  // Top-N events (always included)
  const { data: top10 = [], isLoading: loadingTop10 } = useQuery({
    queryKey: ["top10", id, topN],
    queryFn: () => getTop10(id, undefined, topN),
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
            {t("deepAnalysis.breadcrumb")}
          </span>
        </nav>

        <h1 className="text-2xl font-extrabold tracking-tight text-foreground">
          {t("deepAnalysis.title")}
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
        {t("deepAnalysis.backToEvents")}
      </Link>

      {/* ── Selection summary ── */}
      <div className="flex flex-wrap gap-3 items-center">
        {/* Top-N selector */}
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/30 text-xs">
          <span className="text-blue-700 dark:text-blue-300 font-medium">
            {t("deepAnalysis.topNLabel")}
          </span>
          <select
            value={topN}
            onChange={(e) => setTopN(Number(e.target.value))}
            className="bg-white dark:bg-blue-950/50 border border-blue-300 dark:border-blue-700 rounded px-1.5 py-0.5 text-xs font-bold text-blue-700 dark:text-blue-300 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            {[5, 10, 15, 20, 25, 30, 40, 50].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
          <span className="text-blue-600/70 dark:text-blue-400/70">
            {t("deepAnalysis.topNAlwaysIncluded")}
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
              {t("deepAnalysis.basketCount", { n: basketCount })}
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
            {activeModules.size > 1
              ? t("deepAnalysis.optionalModulesActivePlural", { n: activeModules.size })
              : t("deepAnalysis.optionalModulesActive", { n: activeModules.size })}
          </div>
        )}
      </div>

      {/* ── Event type breakdown (multi-file context) ── */}
      {!loadingTop10 && allEvents.length > 0 && (() => {
        const typeCounts: Record<string, number> = {};
        for (const ev of allEvents) {
          const t = ev.event_type ?? "?";
          typeCounts[t] = (typeCounts[t] ?? 0) + 1;
        }
        const types = Object.entries(typeCounts).sort(([a], [b]) => a.localeCompare(b));
        const hasMultipleTypes = types.length > 1;
        return (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] text-muted-foreground font-medium">{t("deepAnalysis.eventTypes")}</span>
            {types.map(([type, count]) => (
              <span
                key={type}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold border bg-card"
              >
                <span className="font-bold text-foreground">{type}</span>
                <span className="text-muted-foreground">×{count}</span>
              </span>
            ))}
            {hasMultipleTypes && (
              <span className="text-[10px] text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded px-2 py-0.5">
                {t("deepAnalysis.seOnlyNotice")}
              </span>
            )}
          </div>
        );
      })()}

      {/* ── Mutated gene annotation panel ── */}
      <MutatedGenePanel mutatedGenes={mutatedGenes} analysisId={id} />

      {/* ── Loading state ── */}
      {loadingTop10 && (
        <div className="flex items-center gap-2 text-muted-foreground text-sm py-6">
          <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          {t("deepAnalysis.loading")}
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
          {t("deepAnalysis.noEvents")}
        </p>
      )}

      {/* ── 4B — Test de permutation — Significativité ── */}
      <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
        <h2 className="text-sm font-bold text-foreground mb-4">
          {t("deepAnalysis.permutationTitle")}
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
