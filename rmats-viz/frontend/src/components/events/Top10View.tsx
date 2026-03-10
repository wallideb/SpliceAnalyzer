"use client";

/**
 * Top10View
 * ==========
 * Displays the top-10 ranked splicing events with a collapsible left sidebar
 * to switch the annotation mode, and annotated cards that update their content
 * based on the selected mode.
 *
 * The "Interactions" (StringDB) tab is only shown when at least one mutated
 * gene was defined for the analysis.
 */

import { useState } from "react";
import type { SplicingEvent } from "@/types/event";
import type { GeneEntry } from "@/types/gene";
import { SidebarNav } from "@/components/top10/SidebarNav";
import { AnnotatedCard } from "@/components/top10/AnnotatedCard";
import { MotifPatternPanel } from "@/components/top10/MotifPatternPanel";
import { useT } from "@/contexts/LanguageContext";
import type { ViewMode } from "@/components/top10/types";

interface Top10ViewProps {
  events: SplicingEvent[];
  /** Resolved gene entries from the analysis (for ENSG ID hints + StringDB). */
  mutatedGenes?: GeneEntry[];
  /**
   * Optional set of deep-analysis module keys to enable extra sidebar tabs.
   * Supported: "pathways" | "motifs" | "splice"
   * When not provided (Top-10 context) no extra tabs are shown.
   */
  activeModules?: Set<string>;
  /** Analysis UUID — passed to AnnotatedCard (splice view) and MotifPatternPanel. */
  analysisId?: string;
  /** Group labels for direction-of-effect badges (e.g. "Patients" / "Contrôles"). */
  group1Label?: string;
  group2Label?: string;
  /** Deep analysis ID — restricts MotifPatternPanel to significant events. */
  deepAnalysisId?: string;
  /** Pre-set FDR threshold from deep analysis. */
  fdrThreshold?: number;
  /** Pre-set |ΔΨ| min from deep analysis. */
  deltaPsiMin?: number;
}

export function Top10View({ events, mutatedGenes = [], activeModules, analysisId, group1Label, group2Label, deepAnalysisId, fdrThreshold, deltaPsiMin }: Top10ViewProps) {
  const [mode, setMode] = useState<ViewMode>("gene");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const t = useT();

  // StringDB shown only when mutated genes exist.
  // In deep-analysis context also requires "stringdb" in activeModules.
  const showStringDB =
    mutatedGenes.length > 0 &&
    (activeModules === undefined || activeModules.has("stringdb"));

  // Build a symbol → ensembl_id map from the analysis mutated genes list
  const ensemblHints: Record<string, string> = {};
  for (const g of mutatedGenes) {
    ensemblHints[g.symbol.toUpperCase()] = g.ensembl_id;
  }

  if (events.length === 0) {
    return <p className="text-muted-foreground text-sm">{t("top10View.noEvents")}</p>;
  }

  const MODE_LABELS: Record<ViewMode, string> = {
    gene:     t("top10View.modeLabels.gene"),
    go:       t("top10View.modeLabels.go"),
    stringdb: t("top10View.modeLabels.stringdb"),
    pathways: t("top10View.modeLabels.pathways"),
    motifs:   t("top10View.modeLabels.motifs"),
    splice:   t("top10View.modeLabels.splice"),
  };

  return (
    <div className="flex border border-border rounded-xl overflow-hidden shadow-sm bg-card">
      {/* ── Left sidebar ── */}
      <SidebarNav
        activeMode={mode}
        onChange={setMode}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((v) => !v)}
        showStringDB={showStringDB}
        activeModules={activeModules}
      />

      {/* ── Main content ── */}
      <div className="flex-1 min-w-0 p-4">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-4">
          {MODE_LABELS[mode]}
        </p>

        {/* Motifs mode → full-width aggregate panel */}
        {mode === "motifs" && analysisId ? (
          <MotifPatternPanel events={events} analysisId={analysisId} deepAnalysisId={deepAnalysisId} fdrThreshold={fdrThreshold} deltaPsiMin={deltaPsiMin} />
        ) : mode === "motifs" ? (
          <p className="text-xs text-muted-foreground italic">
            {t("top10View.noAnalysisId")}
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-4">
            {events.map((ev) => {
              const symKey = (ev.gene_symbol ?? "").toUpperCase();
              return (
                <AnnotatedCard
                  key={ev.id}
                  event={ev}
                  mode={mode}
                  ensemblIdHint={ensemblHints[symKey] ?? ev.gene_id}
                  mutatedGenes={mutatedGenes}
                  analysisId={analysisId}
                  group1Label={group1Label}
                  group2Label={group2Label}
                />
              );
            })}
          </div>
        )}

        {/* Mode legends */}
        {mode === "go" && (
          <div className="mt-4 flex flex-wrap gap-3 text-xs text-muted-foreground border-t border-border pt-3">
            <span className="font-semibold text-foreground">{t("top10View.goCategories")}</span>
            <span className="flex items-center gap-1"><span className="px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300 text-[11px]">BP</span> {t("top10View.goBP")}</span>
            <span className="flex items-center gap-1"><span className="px-1.5 py-0.5 rounded bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300 text-[11px]">MF</span> {t("top10View.goMF")}</span>
            <span className="flex items-center gap-1"><span className="px-1.5 py-0.5 rounded bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-300 text-[11px]">CC</span> {t("top10View.goCC")}</span>
            <span className="italic">· {t("top10View.goHoverHint")}</span>
          </div>
        )}

        {mode === "stringdb" && (
          <div className="mt-4 flex flex-wrap gap-2 text-xs text-muted-foreground border-t border-border pt-3">
            <span className="font-semibold text-foreground">{t("top10View.stringdbSource")}</span>
            <span>{t("top10View.stringdbDesc")}</span>
          </div>
        )}
      </div>
    </div>
  );
}
