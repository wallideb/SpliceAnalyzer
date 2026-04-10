"use client";

/**
 * Top10View
 * ==========
 * Displays the top-ranked splicing events with a collapsible left sidebar
 * to switch the annotation mode, and annotated cards that update their content
 * based on the selected mode.
 *
 * The "Interactions" (StringDB) tab is only shown when at least one mutated
 * gene was defined for the analysis.
 */

import { useState, useMemo } from "react";
import type { SplicingEvent } from "@/types/event";
import type { GeneEntry } from "@/types/gene";
import { SidebarNav } from "@/components/top10/SidebarNav";
import { AnnotatedCard } from "@/components/top10/AnnotatedCard";
import { MotifPatternPanel } from "@/components/top10/MotifPatternPanel";
import { HnRNPMotifPanel } from "@/components/top10/HnRNPMotifPanel";
import { EnrichrPanel } from "@/components/top10/EnrichrPanel";
import { PatternComparisonPanel } from "@/components/deep-analysis/PatternComparisonPanel";
import { useT } from "@/contexts/LanguageContext";
import type { ViewMode } from "@/components/top10/types";

// ---------------------------------------------------------------------------
// Sort types & helpers
// ---------------------------------------------------------------------------

type SortKey = "default" | "fdr" | "pvalue" | "deltaPsi" | "chr" | "panelapp";

const CHR_ORDER: Record<string, number> = {};
for (let i = 1; i <= 22; i++) CHR_ORDER[`chr${i}`] = i;
CHR_ORDER["chrX"] = 23;
CHR_ORDER["chrY"] = 24;
CHR_ORDER["chrM"] = 25;

function chrNum(chr: string | null | undefined): number {
  if (!chr) return 99;
  const key = chr.startsWith("chr") ? chr : `chr${chr}`;
  return CHR_ORDER[key] ?? 99;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

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
  /** Group labels for direction-of-effect badges (e.g. "Subjects" / "Contrôles"). */
  group1Label?: string;
  group2Label?: string;
  /** Deep analysis ID — restricts MotifPatternPanel to significant events. */
  deepAnalysisId?: string;
  /** Pre-set FDR threshold from deep analysis. */
  fdrThreshold?: number;
  /** Pre-set |ΔΨ| min from deep analysis. */
  deltaPsiMin?: number;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function Top10View({ events, mutatedGenes = [], activeModules, analysisId, group1Label, group2Label, deepAnalysisId, fdrThreshold, deltaPsiMin }: Top10ViewProps) {
  const [mode, setMode] = useState<ViewMode>("gene");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("default");
  const t = useT();

  // StringDB shown only when mutated genes exist.
  const showStringDB =
    mutatedGenes.length > 0 &&
    (activeModules === undefined || activeModules.has("stringdb"));

  // Build a symbol → ensembl_id map from the analysis mutated genes list
  const ensemblHints: Record<string, string> = {};
  for (const g of mutatedGenes) {
    ensemblHints[g.symbol.toUpperCase()] = g.ensembl_id;
  }

  // Sort events — always use gene_symbol then event id as tiebreaker
  // to ensure deterministic ordering across re-renders.
  const sortedEvents = useMemo(() => {
    if (sortKey === "default") return events;
    const copy = [...events];
    const tie = (a: typeof events[0], b: typeof events[0]) =>
      (a.gene_symbol ?? "").localeCompare(b.gene_symbol ?? "") || a.id.localeCompare(b.id);
    switch (sortKey) {
      case "fdr":
        return copy.sort((a, b) => (a.fdr ?? 1) - (b.fdr ?? 1) || tie(a, b));
      case "pvalue":
        return copy.sort((a, b) => (a.p_value ?? 1) - (b.p_value ?? 1) || tie(a, b));
      case "deltaPsi":
        return copy.sort((a, b) => (b.abs_inc_level_diff ?? 0) - (a.abs_inc_level_diff ?? 0) || tie(a, b));
      case "chr":
        return copy.sort((a, b) => chrNum(a.chr) - chrNum(b.chr) || (a.exon_start ?? 0) - (b.exon_start ?? 0) || tie(a, b));
      case "panelapp":
        return copy.sort((a, b) => (a.fdr ?? 1) - (b.fdr ?? 1) || tie(a, b));
      default:
        return copy;
    }
  }, [events, sortKey]);

  if (events.length === 0) {
    return <p className="text-muted-foreground text-sm">{t("top10View.noEvents")}</p>;
  }

  const MODE_LABELS: Record<ViewMode, string> = {
    gene:     t("top10View.modeLabels.gene"),
    stringdb: t("top10View.modeLabels.stringdb"),
    pathways: t("top10View.modeLabels.pathways"),
    motifs:   t("top10View.modeLabels.motifs"),
    splice:   t("top10View.modeLabels.splice"),
    hnrnp:    t("top10View.modeLabels.hnrnp"),
    enrichr:  t("top10View.modeLabels.enrichr"),
  };

  // Show sort controls for gene mode and splice mode
  const showSort = mode === "gene" || mode === "splice";

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

        {/* hnRNP motif enrichment mode → full-width panel */}
        {mode === "hnrnp" && deepAnalysisId ? (
          <HnRNPMotifPanel deepAnalysisId={deepAnalysisId} />
        ) : mode === "hnrnp" ? (
          <p className="text-xs text-muted-foreground italic">
            {t("top10View.noDeepAnalysis")}
          </p>

        /* Enrichr pathway enrichment mode → full-width panel */
        ) : mode === "enrichr" && deepAnalysisId ? (
          <EnrichrPanel deepAnalysisId={deepAnalysisId} />
        ) : mode === "enrichr" ? (
          <p className="text-xs text-muted-foreground italic">
            {t("top10View.noDeepAnalysis")}
          </p>

        /* Motifs mode → full-width aggregate panel */
        ) : mode === "motifs" && analysisId ? (
          <MotifPatternPanel events={events} analysisId={analysisId} deepAnalysisId={deepAnalysisId} fdrThreshold={fdrThreshold} deltaPsiMin={deltaPsiMin} />
        ) : mode === "motifs" ? (
          <p className="text-xs text-muted-foreground italic">
            {t("top10View.noAnalysisId")}
          </p>
        ) : (
          <div className="space-y-6">
            {/* Splice mode: show aggregate pattern comparison panel at the top */}
            {mode === "splice" && deepAnalysisId && (
              <PatternComparisonPanel deepId={deepAnalysisId} />
            )}

            {/* Sort bar — placed between consensus/comparison panels and event cards */}
            {showSort && (
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] text-muted-foreground font-medium">{t("top10View.sortBy")}</span>
                <select
                  value={sortKey}
                  onChange={(e) => setSortKey(e.target.value as SortKey)}
                  className="text-[11px] bg-card border border-border rounded-md px-2 py-1 text-foreground focus:outline-none focus:ring-1 focus:ring-blue-500"
                >
                  <option value="default">{t("top10View.sortOptions.default")}</option>
                  <option value="fdr">{t("top10View.sortOptions.fdr")}</option>
                  <option value="pvalue">{t("top10View.sortOptions.pvalue")}</option>
                  <option value="deltaPsi">{t("top10View.sortOptions.deltaPsi")}</option>
                  <option value="chr">{t("top10View.sortOptions.chr")}</option>
                  <option value="panelapp">{t("top10View.sortOptions.panelapp")}</option>
                </select>
              </div>
            )}

            <div className="grid grid-cols-1 gap-4">
              {sortedEvents.map((ev, idx) => {
                const symKey = (ev.gene_symbol ?? "").toUpperCase();
                return (
                  <AnnotatedCard
                    key={ev.id}
                    event={ev}
                    mode={mode}
                    rank={idx + 1}
                    ensemblIdHint={ensemblHints[symKey] ?? ev.gene_id}
                    mutatedGenes={mutatedGenes}
                    analysisId={analysisId}
                    group1Label={group1Label}
                    group2Label={group2Label}
                  />
                );
              })}
            </div>
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
