"use client";

/**
 * Top10View
 * ==========
 * Displays the top-10 ranked splicing events with:
 *   - A collapsible left sidebar to switch the annotation mode
 *   - Annotated cards that update their content based on the selected mode
 *   - Full dark-mode support throughout
 *
 * Annotation data (PanelApp / GO / UniProt) is fetched lazily per gene
 * and cached for 5 minutes via React Query.
 */

import { useState } from "react";
import type { SplicingEvent } from "@/types/event";
import type { GeneEntry } from "@/types/gene";
import { SidebarNav } from "@/components/top10/SidebarNav";
import { AnnotatedCard } from "@/components/top10/AnnotatedCard";
import type { ViewMode } from "@/components/top10/types";

interface Top10ViewProps {
  events: SplicingEvent[];
  /** Resolved gene entries from the analysis (for ENSG ID hints). */
  mutatedGenes?: GeneEntry[];
}

export function Top10View({ events, mutatedGenes = [] }: Top10ViewProps) {
  const [mode, setMode] = useState<ViewMode>("gene");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // Build a symbol → ensembl_id map from the analysis mutated genes list
  const ensemblHints: Record<string, string> = {};
  for (const g of mutatedGenes) {
    ensemblHints[g.symbol.toUpperCase()] = g.ensembl_id;
  }

  if (events.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">Aucun événement top-10 trouvé.</p>
    );
  }

  const MODE_LABELS: Record<ViewMode, string> = {
    gene:         "Localisation génomique",
    go:           "Ontologie génique (GO)",
    panelapp:     "Panels PanelApp Australia",
    scores:       "Scores rMATS détaillés",
    conservation: "Conservation inter-espèce",
  };

  return (
    <div className="flex border border-border rounded-xl overflow-hidden shadow-sm bg-card">
      {/* ── Left sidebar ── */}
      <SidebarNav
        activeMode={mode}
        onChange={setMode}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((v) => !v)}
      />

      {/* ── Main content ── */}
      <div className="flex-1 min-w-0 p-4">
        {/* Mode label */}
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-4">
          {MODE_LABELS[mode]}
        </p>

        {/* Cards grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {events.map((ev) => {
            const symKey = (ev.gene_symbol ?? "").toUpperCase();
            return (
              <AnnotatedCard
                key={ev.id}
                event={ev}
                mode={mode}
                ensemblIdHint={ensemblHints[symKey] ?? ev.gene_id}
              />
            );
          })}
        </div>

        {/* PanelApp legend (only shown in panelapp mode) */}
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

        {/* GO legend */}
        {mode === "go" && (
          <div className="mt-4 flex flex-wrap gap-3 text-xs text-muted-foreground border-t border-border pt-3">
            <span className="font-semibold text-foreground">Catégories GO :</span>
            <span className="flex items-center gap-1"><span className="px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300 text-[11px]">BP</span> Processus biologique</span>
            <span className="flex items-center gap-1"><span className="px-1.5 py-0.5 rounded bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300 text-[11px]">MF</span> Fonction moléculaire</span>
            <span className="flex items-center gap-1"><span className="px-1.5 py-0.5 rounded bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-300 text-[11px]">CC</span> Composant cellulaire</span>
            <span className="text-muted-foreground italic">· Survolez le nom du gène pour la description UniProt</span>
          </div>
        )}
      </div>
    </div>
  );
}
