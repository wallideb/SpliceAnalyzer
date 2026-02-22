"use client";

/**
 * MutatedGenePanel
 * =================
 * Horizontal strip displayed at the top of Top-10 and Deep Analysis pages.
 *
 * – If no mutated gene was defined for the analysis: one grayed card with
 *   an "Aucun gène candidat sélectionné lors de l'analyse" message.
 *
 * – If one or more mutated genes: one amber card per gene, scrollable
 *   horizontally.  Each card has four inner panels selectable via tabs:
 *
 *     Gene       – ENSG ID, Ensembl link, chromosomal location
 *     GO         – Gene Ontology terms (BP / MF / CC)
 *     PanelApp   – Disease panels (green / amber / red confidence)
 *     Scores rMATS – Total event count in this analysis for this gene
 *
 * Styling: amber (same as the gene tag in the analysis header).
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getGeneAnnotation } from "@/lib/api/annotations";
import { listEvents } from "@/lib/api/events";
import type { GeneEntry } from "@/types/gene";
import type { GeneAnnotation, PanelConfidence } from "@/types/annotation";

// ---------------------------------------------------------------------------
// Sub-panel types
// ---------------------------------------------------------------------------

type GeneTab = "gene" | "go" | "panelapp" | "scores";

const TAB_LABELS: Record<GeneTab, string> = {
  gene:     "Gène",
  go:       "GO",
  panelapp: "PanelApp",
  scores:   "Scores rMATS",
};

// ---------------------------------------------------------------------------
// Style helpers
// ---------------------------------------------------------------------------

const CONFIDENCE_STYLE: Record<PanelConfidence, string> = {
  green:   "bg-green-100 text-green-800 border-green-200 dark:bg-green-900/30 dark:text-green-300 dark:border-green-700",
  amber:   "bg-amber-100 text-amber-800 border-amber-200 dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-700",
  red:     "bg-red-100 text-red-800 border-red-200 dark:bg-red-900/30 dark:text-red-300 dark:border-red-700",
  unknown: "bg-muted text-muted-foreground border-border",
};

const CONF_DOT: Record<PanelConfidence, string> = {
  green:   "bg-green-500",
  amber:   "bg-amber-500",
  red:     "bg-red-500",
  unknown: "bg-muted-foreground",
};

const GO_COLOR: Record<string, string> = {
  BP: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  MF: "bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300",
  CC: "bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-300",
};

// ---------------------------------------------------------------------------
// Inner panel views
// ---------------------------------------------------------------------------

function GeneTabView({ gene, annotation }: { gene: GeneEntry; annotation?: GeneAnnotation }) {
  const ensg = gene.ensembl_id || annotation?.ensembl_id;
  const ensemblUrl = ensg
    ? `https://www.ensembl.org/Homo_sapiens/Gene/Summary?g=${ensg}`
    : null;

  return (
    <div className="space-y-2 text-xs">
      {ensg && (
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-amber-700 dark:text-amber-400 font-medium">ENSG :</span>
          {ensemblUrl ? (
            <a href={ensemblUrl} target="_blank" rel="noopener noreferrer"
              className="font-mono text-blue-600 dark:text-blue-400 hover:underline">
              {ensg}
            </a>
          ) : (
            <span className="font-mono text-foreground">{ensg}</span>
          )}
        </div>
      )}
      {annotation?.protein_function && (
        <p className="text-[11px] text-amber-800 dark:text-amber-300 leading-relaxed line-clamp-4">
          {annotation.protein_function.function}
        </p>
      )}
      {ensemblUrl && (
        <a href={ensemblUrl} target="_blank" rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-[11px] text-blue-600 dark:text-blue-400 hover:underline">
          <ExternalIcon /> Voir sur Ensembl
        </a>
      )}
    </div>
  );
}

function GOTabView({ annotation, isLoading }: { annotation?: GeneAnnotation; isLoading: boolean }) {
  if (isLoading) return <Skeleton rows={3} />;
  const terms = annotation?.go_terms ?? [];
  if (!terms.length) return <Empty text="Aucun terme GO disponible." />;

  const grouped = terms.reduce<Record<string, typeof terms>>((acc, t) => {
    (acc[t.category] ||= []).push(t);
    return acc;
  }, {});

  return (
    <div className="space-y-2">
      {(["BP", "MF", "CC"] as const).map((cat) => {
        const catTerms = grouped[cat];
        if (!catTerms?.length) return null;
        return (
          <div key={cat}>
            <p className="text-[10px] font-semibold text-amber-700 dark:text-amber-400 uppercase tracking-wide mb-1">
              {cat === "BP" ? "Processus biol." : cat === "MF" ? "Fonction mol." : "Composant cell."}
            </p>
            <div className="flex flex-wrap gap-1">
              {catTerms.slice(0, 3).map((t) => (
                <a key={t.id} href={`https://www.ebi.ac.uk/QuickGO/term/${t.id}`}
                  target="_blank" rel="noopener noreferrer" title={t.id}
                  className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] border font-medium hover:opacity-80 ${GO_COLOR[cat] ?? "bg-muted text-foreground"}`}>
                  {t.term}
                </a>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function PanelAppTabView({ annotation, isLoading }: { annotation?: GeneAnnotation; isLoading: boolean }) {
  if (isLoading) return <Skeleton rows={2} />;
  const panels = annotation?.panels ?? [];
  if (!panels.length) return <Empty text="Aucun panel PanelApp trouvé." />;

  return (
    <div className="space-y-1.5">
      {panels.slice(0, 3).map((p) => {
        const conf = p.confidence_label as PanelConfidence;
        return (
          <div key={p.panel_name}
            className={`flex items-start gap-2 px-2 py-1.5 rounded-lg border text-[11px] ${CONFIDENCE_STYLE[conf]}`}>
            <span className={`mt-0.5 w-2 h-2 rounded-full shrink-0 ${CONF_DOT[conf]}`} />
            <div className="min-w-0">
              <p className="font-semibold leading-tight line-clamp-2">{p.panel_name}</p>
              {p.disorders.length > 0 && (
                <p className="opacity-75 mt-0.5 text-[10px] truncate">
                  {p.disorders.slice(0, 2).join(", ")}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ScoresTabView({
  symbol,
  analysisId,
}: {
  symbol: string;
  analysisId?: string;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["gene-event-count", analysisId, symbol],
    queryFn: () =>
      listEvents(analysisId!, { gene_symbol: symbol, page_size: 1, fdr_max: 0.05 }),
    enabled: !!analysisId,
    staleTime: 5 * 60 * 1000,
  });

  const { data: allData, isLoading: loadingAll } = useQuery({
    queryKey: ["gene-event-count-all", analysisId, symbol],
    queryFn: () => listEvents(analysisId!, { gene_symbol: symbol, page_size: 1 }),
    enabled: !!analysisId,
    staleTime: 5 * 60 * 1000,
  });

  if (!analysisId) return <Empty text="Contexte d'analyse non disponible." />;

  return (
    <div className="space-y-2 text-xs">
      <div className="grid grid-cols-2 gap-2">
        <div className="bg-amber-50 dark:bg-amber-900/40 border border-amber-200 dark:border-amber-600 rounded-lg px-2.5 py-2 text-center">
          <p className="text-[10px] text-amber-700 dark:text-amber-400 font-medium">Évén. significatifs</p>
          <p className="text-lg font-extrabold text-amber-800 dark:text-amber-300 tabular-nums">
            {isLoading ? "…" : (data?.total.toLocaleString("fr-FR") ?? "—")}
          </p>
          <p className="text-[10px] text-amber-600 dark:text-amber-500">FDR &lt; 0.05</p>
        </div>
        <div className="bg-amber-50 dark:bg-amber-900/40 border border-amber-200 dark:border-amber-600 rounded-lg px-2.5 py-2 text-center">
          <p className="text-[10px] text-amber-700 dark:text-amber-400 font-medium">Total événements</p>
          <p className="text-lg font-extrabold text-amber-800 dark:text-amber-300 tabular-nums">
            {loadingAll ? "…" : (allData?.total.toLocaleString("fr-FR") ?? "—")}
          </p>
          <p className="text-[10px] text-amber-600 dark:text-amber-500">toutes catégories</p>
        </div>
      </div>
      <p className="text-[10px] text-muted-foreground italic">
        Scores détaillés disponibles dans le tableau des événements.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared mini helpers
// ---------------------------------------------------------------------------

function Skeleton({ rows }: { rows: number }) {
  return (
    <div className="space-y-1.5">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-5 rounded bg-amber-200/50 dark:bg-amber-800/30 animate-pulse" />
      ))}
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="text-[11px] text-amber-700 dark:text-amber-400 italic">{text}</p>;
}

function ExternalIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Single gene card
// ---------------------------------------------------------------------------

function GeneCard({
  gene,
  analysisId,
  fullWidth = false,
}: {
  gene: GeneEntry;
  analysisId?: string;
  fullWidth?: boolean;
}) {
  const [tab, setTab] = useState<GeneTab>("gene");

  const { data: annotation, isLoading } = useQuery({
    queryKey: ["annotation", gene.symbol, gene.ensembl_id],
    queryFn: () => getGeneAnnotation(gene.symbol, gene.ensembl_id),
    staleTime: 5 * 60 * 1000,
  });

  return (
    <div className={`${fullWidth ? "w-full" : "shrink-0 w-72"} flex flex-col border-2 border-amber-400 dark:border-amber-600 rounded-xl bg-gradient-to-b from-amber-50 to-white dark:from-amber-950/70 dark:to-amber-950/50 shadow-md hover:shadow-lg transition-shadow overflow-hidden`}>
      {/* Card header – gradient for depth */}
      <div className="px-4 py-3 border-b-2 border-amber-300 dark:border-amber-600 bg-gradient-to-r from-amber-200 to-amber-100 dark:from-amber-800/70 dark:to-amber-900/60">
        <div className="flex items-center gap-2">
          <span className="w-5 h-5 flex items-center justify-center rounded-full bg-amber-500 text-white text-[10px] font-bold shrink-0">
            <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" />
            </svg>
          </span>
          <p className="font-extrabold text-sm text-amber-900 dark:text-amber-100">
            {gene.symbol}
          </p>
        </div>
        {gene.ensembl_id && (
          <p className="text-[10px] font-mono text-amber-700 dark:text-amber-400 truncate mt-0.5 pl-7">
            {gene.ensembl_id}
          </p>
        )}
      </div>

      {/* Tab strip */}
      <div className="flex border-b border-amber-200 dark:border-amber-700 bg-amber-50/60 dark:bg-amber-950/40">
        {(Object.keys(TAB_LABELS) as GeneTab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 py-1.5 text-[10px] font-semibold transition-colors ${
              tab === t
                ? "text-amber-900 dark:text-amber-200 border-b-2 border-amber-500 dark:border-amber-400 bg-white dark:bg-amber-900/20"
                : "text-amber-600 dark:text-amber-500 hover:text-amber-800 dark:hover:text-amber-300"
            }`}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 p-3 overflow-y-auto min-h-[120px] max-h-[180px]">
        {tab === "gene"     && <GeneTabView gene={gene} annotation={annotation} />}
        {tab === "go"       && <GOTabView annotation={annotation} isLoading={isLoading} />}
        {tab === "panelapp" && <PanelAppTabView annotation={annotation} isLoading={isLoading} />}
        {tab === "scores"   && <ScoresTabView symbol={gene.symbol} analysisId={analysisId} />}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty-state card (no mutated gene selected)
// ---------------------------------------------------------------------------

function NoGeneCard() {
  return (
    <div className="flex items-center gap-4 border-2 border-dashed border-muted rounded-xl bg-muted/10 dark:bg-muted/5 px-6 py-4">
      <svg xmlns="http://www.w3.org/2000/svg" className="w-7 h-7 text-muted-foreground/30 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <div>
        <p className="text-sm font-semibold text-muted-foreground">
          Aucun gène candidat sélectionné lors de l&apos;analyse
        </p>
        <p className="text-[11px] text-muted-foreground/60 mt-0.5">
          Ajoutez un gène muté lors de la création ou modification de l&apos;analyse
          pour activer les annotations et l&apos;onglet Interactions STRING-DB.
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------

interface MutatedGenePanelProps {
  /** Resolved mutated gene entries for this analysis. */
  mutatedGenes: GeneEntry[];
  /** Analysis ID, used to fetch per-gene rMATS event counts. */
  analysisId?: string;
  /**
   * "horizontal" (default): scrollable horizontal strip with section wrapper.
   * "vertical": stacked vertically, full-width cards, no section wrapper
   *             (caller is responsible for the container/heading).
   */
  layout?: "horizontal" | "vertical";
}

export function MutatedGenePanel({ mutatedGenes, analysisId, layout = "horizontal" }: MutatedGenePanelProps) {
  // ── Vertical sidebar mode ────────────────────────────────────────────────
  if (layout === "vertical") {
    return (
      <div className="space-y-3">
        {mutatedGenes.length === 0 ? (
          <NoGeneCard />
        ) : (
          mutatedGenes.map((gene) => (
            <GeneCard key={gene.ensembl_id || gene.symbol} gene={gene} analysisId={analysisId} fullWidth />
          ))
        )}
      </div>
    );
  }

  // ── Horizontal strip mode (default) ─────────────────────────────────────
  return (
    <section aria-label="Gènes candidats" className="bg-amber-50/30 dark:bg-amber-950/30 border border-amber-200/60 dark:border-amber-700/60 rounded-xl p-4">
      <p className="text-xs font-semibold text-amber-700 dark:text-amber-400 uppercase tracking-wide mb-3 flex items-center gap-1.5">
        <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" />
        </svg>
        Gène{mutatedGenes.length !== 1 ? "s" : ""} candidat{mutatedGenes.length !== 1 ? "s" : ""}
        {mutatedGenes.length > 0 && (
          <span className="ml-1 font-normal normal-case text-amber-600 dark:text-amber-500">
            — cliquez sur un onglet pour explorer les annotations
          </span>
        )}
      </p>

      {mutatedGenes.length === 0 ? (
        <NoGeneCard />
      ) : (
        <div className="flex gap-3 overflow-x-auto pb-1 snap-x snap-mandatory"
          style={{ scrollbarWidth: "thin", scrollbarColor: "rgb(251 191 36 / 0.4) transparent" }}
        >
          {mutatedGenes.map((gene) => (
            <div key={gene.ensembl_id || gene.symbol} className="snap-start">
              <GeneCard gene={gene} analysisId={analysisId} />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
