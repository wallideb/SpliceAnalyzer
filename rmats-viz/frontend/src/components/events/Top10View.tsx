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
}

export function Top10View({ events, mutatedGenes = [], activeModules }: Top10ViewProps) {
  const [mode, setMode] = useState<ViewMode>("gene");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

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
    return <p className="text-muted-foreground text-sm">Aucun événement top-10 trouvé.</p>;
  }

  const MODE_LABELS: Record<ViewMode, string> = {
    gene:     "Localisation génomique",
    go:       "Ontologie génique (GO)",
    panelapp: "Panels PanelApp Australia",
    scores:   "Scores rMATS détaillés",
    stringdb: "Interactions STRING-DB avec le gène muté",
    pathways: "Voies moléculaires (à venir)",
    motifs:   "Motifs récurrents (à venir)",
    splice:   "Sites consensus d'épissage (à venir)",
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

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {events.map((ev) => {
            const symKey = (ev.gene_symbol ?? "").toUpperCase();
            return (
              <AnnotatedCard
                key={ev.id}
                event={ev}
                mode={mode}
                ensemblIdHint={ensemblHints[symKey] ?? ev.gene_id}
                mutatedGenes={mutatedGenes}
              />
            );
          })}
        </div>

        {/* Mode legends */}
        {mode === "panelapp" && (
          <div className="mt-4 flex flex-wrap gap-3 text-xs text-muted-foreground border-t border-border pt-3">
            <span className="font-semibold text-foreground">Niveau de confiance PanelApp :</span>
            {(["green", "amber", "red"] as const).map((c) => (
              <span key={c} className="flex items-center gap-1.5">
                <span className={`w-2 h-2 rounded-full ${c === "green" ? "bg-green-500" : c === "amber" ? "bg-amber-500" : "bg-red-500"}`} />
                {c === "green" ? "Vert – haute confiance" : c === "amber" ? "Ambre – confiance modérée" : "Rouge – faible confiance"}
              </span>
            ))}
          </div>
        )}

        {mode === "go" && (
          <div className="mt-4 flex flex-wrap gap-3 text-xs text-muted-foreground border-t border-border pt-3">
            <span className="font-semibold text-foreground">Catégories GO :</span>
            <span className="flex items-center gap-1"><span className="px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300 text-[11px]">BP</span> Processus biologique</span>
            <span className="flex items-center gap-1"><span className="px-1.5 py-0.5 rounded bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300 text-[11px]">MF</span> Fonction moléculaire</span>
            <span className="flex items-center gap-1"><span className="px-1.5 py-0.5 rounded bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-300 text-[11px]">CC</span> Composant cellulaire</span>
            <span className="italic">· Survolez le nom du gène pour la description UniProt</span>
          </div>
        )}

        {mode === "stringdb" && (
          <div className="mt-4 flex flex-wrap gap-2 text-xs text-muted-foreground border-t border-border pt-3">
            <span className="font-semibold text-foreground">Source :</span>
            <span>STRING-DB v12 · réseau de preuve d&apos;interaction protéine–protéine · cliquez sur l&apos;image pour ouvrir STRING.</span>
          </div>
        )}
      </div>
    </div>
  );
}
