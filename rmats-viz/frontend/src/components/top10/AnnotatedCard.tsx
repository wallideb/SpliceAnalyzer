"use client";

/**
 * AnnotatedCard
 * ==============
 * A single Top-10 splicing event card with dynamic content driven by the
 * selected sidebar mode.
 *
 * The card always shows:
 *   - Top-rank badge (blue circle)
 *   - Gene symbol (with hover tooltip for UniProt protein function)
 *   - Event type badge
 *   - FDR + ΔPSI summary row
 *
 * The lower section changes based on `mode`:
 *   gene     – ENSG ID, coordinates, Ensembl link
 *   go       – GO terms (BP / MF / CC) from mygene.info
 *   panelapp – Disease panels (green / amber / red) from PanelApp AU
 *   scores   – Full rMATS statistics + read counts
 *   stringdb – STRING-DB protein interaction network with the mutated gene
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getGeneAnnotation, getGeneInteractions } from "@/lib/api/annotations";
import { EventTypeBadge } from "@/components/events/EventTypeBadge";
import { formatFDR, formatDeltaPSI, formatCoord } from "@/lib/utils";
import { useT } from "@/contexts/LanguageContext";
import type { SplicingEvent } from "@/types/event";
import type { GeneAnnotation, GeneInteraction, PanelConfidence } from "@/types/annotation";
import type { GeneEntry } from "@/types/gene";
import type { ViewMode } from "./types";
import { SpliceView } from "./SpliceView";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface AnnotatedCardProps {
  event: SplicingEvent;
  mode: ViewMode;
  /** Pre-resolved Ensembl ID for this gene (from the analysis mutated_genes list). */
  ensemblIdHint?: string | null;
  /** Mutated genes from the analysis, used for StringDB interaction view. */
  mutatedGenes: GeneEntry[];
  /** Analysis UUID — needed by SpliceView to trigger bulk feature computation. */
  analysisId?: string;
  /** Group labels (e.g. "Subjects" / "Contrôles") for direction-of-effect badges. */
  group1Label?: string;
  group2Label?: string;
  /** 1-based display rank for sorting feedback. */
  rank?: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const CONFIDENCE_STYLES: Record<PanelConfidence, string> = {
  green:   "bg-green-100 text-green-800 border-green-200 dark:bg-green-900/30 dark:text-green-300 dark:border-green-800",
  amber:   "bg-amber-100 text-amber-800 border-amber-200 dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-800",
  red:     "bg-red-100 text-red-800 border-red-200 dark:bg-red-900/30 dark:text-red-300 dark:border-red-800",
  unknown: "bg-muted text-muted-foreground border-border",
};

const CONFIDENCE_DOT: Record<PanelConfidence, string> = {
  green:   "bg-green-500",
  amber:   "bg-amber-500",
  red:     "bg-red-500",
  unknown: "bg-muted-foreground",
};

const GO_CATEGORY_KEYS: Record<string, string> = {
  BP: "annotatedCard.go.categories.BP",
  MF: "annotatedCard.go.categories.MF",
  CC: "annotatedCard.go.categories.CC",
};

const GO_CATEGORY_COLOR: Record<string, string> = {
  BP: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  MF: "bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300",
  CC: "bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-300",
};

function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-muted ${className}`} />;
}

// ---------------------------------------------------------------------------
// Sub-views
// ---------------------------------------------------------------------------

function GeneView({ ev, annotation }: { ev: SplicingEvent; annotation?: GeneAnnotation }) {
  const t = useT();
  const ensgId = annotation?.ensembl_id ?? ev.gene_id ?? null;
  const ensemblLink = ensgId
    ? `https://www.ensembl.org/Homo_sapiens/Gene/Summary?g=${ensgId}`
    : null;

  const incL1 = ev.inc_level_1?.split(",").map(Number).filter((v) => !isNaN(v)) ?? [];
  const incL2 = ev.inc_level_2?.split(",").map(Number).filter((v) => !isNaN(v)) ?? [];
  const mean = (arr: number[]) =>
    arr.length ? (arr.reduce((a, b) => a + b, 0) / arr.length).toFixed(3) : "—";

  return (
    <div className="space-y-3 text-sm">
      {/* rMATS scores */}
      <div className="grid grid-cols-3 gap-x-4 gap-y-1.5 text-xs">
        <StatRow label="FDR" value={formatFDR(ev.fdr)} highlight />
        <StatRow label="p-value" value={ev.p_value != null ? ev.p_value.toExponential(2) : "—"} />
        <StatRow label="|ΔPSI|" value={ev.abs_inc_level_diff?.toFixed(3) ?? "—"} />
        <StatRow label={t("annotatedCard.scores.meanPsi1")} value={mean(incL1)} />
        <StatRow label={t("annotatedCard.scores.meanPsi2")} value={mean(incL2)} />
        <StatRow label="ΔPSI" value={formatDeltaPSI(ev.inc_level_difference)} highlight />
      </div>

      {/* Gene info */}
      {ensgId && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-muted-foreground text-xs">{t("annotatedCard.gene.ensg")}</span>
          {ensemblLink ? (
            <a href={ensemblLink} target="_blank" rel="noopener noreferrer"
              className="font-mono text-xs text-blue-600 dark:text-blue-400 hover:underline">
              {ensgId}
            </a>
          ) : (
            <span className="font-mono text-xs text-foreground">{ensgId}</span>
          )}
        </div>
      )}
      <div className="text-xs text-muted-foreground bg-muted/40 dark:bg-slate-700/40 rounded px-3 py-2 space-y-0.5">
        <div><span className="font-medium text-foreground">{t("annotatedCard.gene.chr")}</span>{" "}{ev.chr ?? "?"} {ev.strand ? t("annotatedCard.gene.strand", { s: ev.strand }) : ""}</div>
        <div><span className="font-medium text-foreground">{t("annotatedCard.gene.exon")}</span>{" "}{formatCoord(ev.exon_start)} – {formatCoord(ev.exon_end)}</div>
        <div><span className="font-medium text-foreground">{t("annotatedCard.gene.upstream")}</span>{" "}{formatCoord(ev.upstream_es)} – {formatCoord(ev.upstream_ee)}</div>
        <div><span className="font-medium text-foreground">{t("annotatedCard.gene.downstream")}</span>{" "}{formatCoord(ev.downstream_es)} – {formatCoord(ev.downstream_ee)}</div>
      </div>
      {ensemblLink && (
        <a href={ensemblLink} target="_blank" rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline">
          <ExternalIcon />
          {t("annotatedCard.gene.viewEnsembl")}
        </a>
      )}
    </div>
  );
}

function GOView({ annotation, isLoading }: { annotation?: GeneAnnotation; isLoading: boolean }) {
  const t = useT();
  if (isLoading) {
    return <div className="space-y-2">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-6 w-full" />)}</div>;
  }
  const terms = annotation?.go_terms ?? [];
  if (terms.length === 0) {
    return <p className="text-xs text-muted-foreground italic">{t("annotatedCard.go.noTerms")}</p>;
  }
  const grouped = terms.reduce<Record<string, typeof terms>>((acc, term) => {
    if (!acc[term.category]) acc[term.category] = [];
    acc[term.category].push(term);
    return acc;
  }, {});

  return (
    <div className="space-y-2">
      {(["BP", "MF", "CC"] as const).map((cat) => {
        const catTerms = grouped[cat];
        if (!catTerms?.length) return null;
        return (
          <div key={cat}>
            <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">
              {t(GO_CATEGORY_KEYS[cat])}
            </p>
            <div className="flex flex-wrap gap-1">
              {catTerms.slice(0, 4).map((term) => (
                <a key={term.id} href={`https://www.ebi.ac.uk/QuickGO/term/${term.id}`}
                  target="_blank" rel="noopener noreferrer"
                  title={`${term.id} · Evidence: ${term.evidence || "–"}`}
                  className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] border font-medium hover:opacity-80 transition-opacity ${GO_CATEGORY_COLOR[cat] ?? "bg-muted text-foreground"}`}>
                  {term.term}
                </a>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function PanelAppView({ annotation, isLoading }: { annotation?: GeneAnnotation; isLoading: boolean }) {
  const t = useT();
  if (isLoading) {
    return <div className="space-y-2">{[1, 2].map((i) => <Skeleton key={i} className="h-8 w-full" />)}</div>;
  }
  const panels = annotation?.panels ?? [];
  if (panels.length === 0) {
    return <p className="text-xs text-muted-foreground italic">{t("annotatedCard.panelapp.noPanel")}</p>;
  }
  return (
    <div className="space-y-1.5">
      {panels.slice(0, 4).map((panel) => {
        const conf = panel.confidence_label as PanelConfidence;
        return (
          <div key={panel.panel_name}
            className={`flex items-start gap-2 px-2.5 py-2 rounded-lg border text-xs ${CONFIDENCE_STYLES[conf]}`}>
            <span className={`mt-0.5 w-2 h-2 rounded-full shrink-0 ${CONFIDENCE_DOT[conf]}`} />
            <div className="min-w-0">
              <p className="font-semibold leading-tight">{panel.panel_name}</p>
              {panel.disorders.length > 0 && (
                <p className="text-[11px] opacity-75 mt-0.5 truncate">
                  {panel.disorders.slice(0, 2).join(", ")}
                </p>
              )}
            </div>
          </div>
        );
      })}
      <a href={`https://panelapp.agha.umccr.org/panels/entities/${encodeURIComponent(annotation?.symbol ?? "")}/`}
        target="_blank" rel="noopener noreferrer"
        className="inline-flex items-center gap-1 text-[11px] text-blue-600 dark:text-blue-400 hover:underline mt-1">
        <ExternalIcon />
        {t("annotatedCard.panelapp.viewPanelApp")}
      </a>
    </div>
  );
}


// ---------------------------------------------------------------------------
// STRING-DB custom SVG diagram helpers
// ---------------------------------------------------------------------------

/**
 * InteractionDiagram
 * Renders a custom SVG network diagram styled after STRING-DB:
 *   - Two circular nodes (mutated gene left, event gene right)
 *   - One colored Bézier arc per active evidence channel
 *   - Arc thickness proportional to score (thicker = stronger evidence)
 */
function InteractionDiagram({ interaction }: { interaction: GeneInteraction }) {
  const W = 300, H = 160;
  const cx1 = 65, cx2 = 235, cy = 80, r = 36;

  const meta = interaction.channel_meta;
  const n = meta.length;

  // Spread arcs vertically so they don't overlap
  const spacing = Math.min(18, n > 1 ? 80 / (n - 1) : 0);
  const startOffset = n > 1 ? -((n - 1) * spacing) / 2 : 0;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full max-w-[280px] mx-auto"
      aria-label={`Interaction STRING-DB : ${interaction.gene_a} – ${interaction.gene_b}`}
    >
      {/* Colored Bézier arcs, one per evidence channel */}
      {meta.map((ch, i) => {
        const score = interaction.channels[ch.key] ?? 0;
        // Stroke width: 1.5 (min) → 5.5 (max at score=1)
        const sw = 1.5 + score * 4;
        const cpY = cy + startOffset + i * spacing;
        // Cubic Bézier: start at right edge of left circle, end at left edge of right circle
        const x1 = cx1 + r, x2 = cx2 - r;
        const d = `M ${x1} ${cy} C ${x1 + 45} ${cpY}, ${x2 - 45} ${cpY}, ${x2} ${cy}`;
        return (
          <path
            key={ch.key}
            d={d}
            fill="none"
            stroke={ch.color}
            strokeWidth={sw}
            strokeOpacity={0.8}
            strokeLinecap="round"
          />
        );
      })}

      {/* Left node – mutated gene (amber) */}
      <circle cx={cx1} cy={cy} r={r} fill="#FFC000" fillOpacity={0.15} stroke="#FFC000" strokeWidth={2.5} />
      <text x={cx1} y={cy} dominantBaseline="middle" textAnchor="middle"
        fontSize={interaction.gene_a.length > 5 ? 8 : 10} fontWeight="700" fill="currentColor">
        {interaction.gene_a}
      </text>

      {/* Right node – event gene (blue) */}
      <circle cx={cx2} cy={cy} r={r} fill="#1F77B4" fillOpacity={0.15} stroke="#1F77B4" strokeWidth={2.5} />
      <text x={cx2} y={cy} dominantBaseline="middle" textAnchor="middle"
        fontSize={interaction.gene_b.length > 5 ? 8 : 10} fontWeight="700" fill="currentColor">
        {interaction.gene_b}
      </text>
    </svg>
  );
}

/**
 * SingleInteraction
 * Fetches and renders the STRING-DB result for ONE mutated gene / event gene pair.
 */
function SingleInteraction({
  mutatedSymbol,
  eventSymbol,
}: {
  mutatedSymbol: string;
  eventSymbol: string;
}) {
  const { data, isLoading, isError } = useQuery<GeneInteraction>({
    queryKey: ["stringdb", mutatedSymbol, eventSymbol],
    queryFn: () => getGeneInteractions(mutatedSymbol, eventSymbol),
    staleTime: 5 * 60 * 1000,
  });

  // Pair label header
  const pairLabel = (
    <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground mb-2">
      <span className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300 border border-amber-200 dark:border-amber-700">
        {mutatedSymbol}
      </span>
      <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
      </svg>
      <span className="px-1.5 py-0.5 rounded bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300 border border-blue-200 dark:border-blue-700">
        {eventSymbol}
      </span>
    </div>
  );

  const t = useT();

  if (isLoading) {
    return (
      <div>
        {pairLabel}
        <div className="space-y-1.5">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-4 w-3/4" />
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div>
        {pairLabel}
        <p className="text-[11px] text-muted-foreground italic">
          {t("annotatedCard.stringdb.error")}
        </p>
      </div>
    );
  }

  if (!data.has_interaction) {
    return (
      <div>
        {pairLabel}
        <p className="text-[11px] text-muted-foreground italic">
          {t("annotatedCard.stringdb.noInteraction")}
        </p>
      </div>
    );
  }

  // Combined score as percentage
  const scorePercent = Math.round(data.combined_score * 1000) / 10;

  return (
    <div className="space-y-3">
      {pairLabel}

      {/* SVG network diagram */}
      <InteractionDiagram interaction={data} />

      {/* Score summary */}
      <div className="text-center text-[11px] text-muted-foreground">
        {t("annotatedCard.stringdb.combinedScore")}{" "}
        <span className="font-semibold text-foreground">{scorePercent}%</span>
      </div>

      {/* Evidence table */}
      <div className="space-y-1">
        <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
          {t("annotatedCard.stringdb.evidence")}
        </p>
        <div className="divide-y divide-border rounded-lg border border-border overflow-hidden text-[11px]">
          {data.channel_meta.map((ch) => {
            const score = data.channels[ch.key] ?? 0;
            const pct = Math.round(score * 1000) / 10;
            return (
              <div key={ch.key} className="flex items-center gap-2 px-2.5 py-1.5 bg-card dark:bg-slate-800/60">
                <span
                  className="w-2.5 h-2.5 rounded-full shrink-0"
                  style={{ backgroundColor: ch.color }}
                />
                <span className="flex-1 text-foreground">{ch.label}</span>
                <span className="font-semibold text-foreground tabular-nums">{pct}%</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* PMIDs section (only when text-mining evidence exists) */}
      {data.pmids.length > 0 && (
        <div className="space-y-1">
          <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
            {t("annotatedCard.stringdb.publications")}
          </p>
          <ul className="space-y-1.5">
            {data.pmids.map((pub) => (
              <li key={pub.pmid} className="text-[11px]">
                <a
                  href={`https://pubmed.ncbi.nlm.nih.gov/${pub.pmid}/`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-start gap-1 text-blue-600 dark:text-blue-400 hover:underline leading-snug"
                >
                  <ExternalIcon />
                  <span>
                    <span className="font-semibold">PMID: {pub.pmid}</span>
                    {pub.year ? ` (${pub.year})` : ""}
                    {pub.title ? ` – ${pub.title}` : ""}
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Link to STRING-DB */}
      <a
        href={data.string_url}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 text-[11px] text-blue-600 dark:text-blue-400 hover:underline"
      >
        <ExternalIcon />
        {t("annotatedCard.stringdb.openStringDB")}
      </a>
    </div>
  );
}

/**
 * StringDBView
 * Iterates over all mutated genes and shows one STRING-DB interaction
 * panel per (mutated gene, event gene) pair. Self-pairs are skipped.
 */
function StringDBView({
  eventSymbol,
  mutatedGenes,
}: {
  eventSymbol: string;
  mutatedGenes: GeneEntry[];
}) {
  const t = useT();
  if (!eventSymbol) {
    return (
      <p className="text-xs text-muted-foreground italic">
        {t("annotatedCard.stringdb.noSymbol")}
      </p>
    );
  }

  // Deduplicate and skip self-interactions
  const pairs = mutatedGenes.filter(
    (g) => g.symbol.toUpperCase() !== eventSymbol.toUpperCase(),
  );

  if (pairs.length === 0) {
    return (
      <p className="text-xs text-muted-foreground italic">
        {t("annotatedCard.stringdb.selfInteraction")}
      </p>
    );
  }

  return (
    <div className="space-y-5">
      {pairs.map((mutGene) => (
        <SingleInteraction
          key={mutGene.symbol}
          mutatedSymbol={mutGene.symbol}
          eventSymbol={eventSymbol}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// PanelApp badge (replaces the dedicated sidebar tab)
// ---------------------------------------------------------------------------

/** Highest-confidence level across all panels for this gene. */
function topPanelConfidence(panels: GeneAnnotation["panels"]): PanelConfidence | null {
  if (!panels?.length) return null;
  if (panels.some((p) => p.confidence_label === "green")) return "green";
  if (panels.some((p) => p.confidence_label === "amber")) return "amber";
  if (panels.some((p) => p.confidence_label === "red"))   return "red";
  return "unknown";
}

const PANEL_BADGE_STYLE: Record<PanelConfidence, string> = {
  green:   "bg-green-500 text-white",
  amber:   "bg-amber-400 text-white",
  red:     "bg-red-500 text-white",
  unknown: "bg-muted text-muted-foreground",
};

function PanelAppBadge({ annotation }: { annotation?: GeneAnnotation }) {
  const t = useT();
  const [show, setShow] = useState(false);
  const conf = topPanelConfidence(annotation?.panels ?? []);
  if (!conf || conf === "unknown") return null;

  const panels = annotation!.panels!;
  return (
    <div className="relative">
      <button
        type="button"
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold tracking-wide leading-none select-none ${PANEL_BADGE_STYLE[conf]}`}
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="w-2.5 h-2.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
        </svg>
        PanelApp
      </button>

      {show && (
        <div className="absolute right-0 top-full mt-1 z-50 w-64 bg-card border border-border rounded-lg shadow-xl p-2.5 space-y-1.5">
          <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">
            {t("annotatedCard.panelapp.diseasePanels")}
          </p>
          {panels.slice(0, 6).map((panel) => {
            const c = panel.confidence_label as PanelConfidence;
            return (
              <div key={panel.panel_name} className={`flex items-start gap-1.5 px-2 py-1.5 rounded text-xs border ${CONFIDENCE_STYLES[c]}`}>
                <span className={`mt-0.5 w-2 h-2 rounded-full shrink-0 ${CONFIDENCE_DOT[c]}`} />
                <span className="font-medium leading-tight">{panel.panel_name}</span>
              </div>
            );
          })}
          {panels.length > 6 && (
            <p className="text-[11px] text-muted-foreground text-right">
              {panels.length - 6 > 1
                ? t("annotatedCard.panelapp.morePanelsPlural", { n: panels.length - 6 })
                : t("annotatedCard.panelapp.morePanels", { n: panels.length - 6 })}…
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Coming-soon stub for deep-analysis modules not yet implemented
// ---------------------------------------------------------------------------

const COMING_SOON_LABEL_KEYS: Partial<Record<ViewMode, string>> = {
  pathways: "sidebarNav.tabs.pathways",
  motifs:   "sidebarNav.tabs.motifs",
};

function ComingSoonView({ mode }: { mode: ViewMode }) {
  const t = useT();
  const label = COMING_SOON_LABEL_KEYS[mode] ? t(COMING_SOON_LABEL_KEYS[mode]!) : mode;
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-6 text-center">
      <svg xmlns="http://www.w3.org/2000/svg" className="w-8 h-8 text-muted-foreground/40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <p className="text-sm font-semibold text-foreground">{t("annotatedCard.comingSoon")}</p>
      <p
        className="text-[11px] text-muted-foreground max-w-[180px] leading-relaxed"
        dangerouslySetInnerHTML={{ __html: t("annotatedCard.comingSoonModule", { label }) }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

function StatRow({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div>
      <dt className="text-[10px] text-muted-foreground">{label}</dt>
      <dd className={`font-semibold text-xs ${highlight ? "text-foreground" : "text-muted-foreground"}`}>{value}</dd>
    </div>
  );
}

function ExternalIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
    </svg>
  );
}

function GeneSymbolWithTooltip({
  symbol,
  annotation,
}: {
  symbol: string;
  annotation?: GeneAnnotation;
}) {
  const [show, setShow] = useState(false);
  const func = annotation?.protein_function;

  return (
    <div className="relative inline-block">
      <span
        className={`font-bold text-base text-foreground ${func ? "cursor-help underline decoration-dotted decoration-muted-foreground underline-offset-2" : ""}`}
        onMouseEnter={() => func && setShow(true)}
        onMouseLeave={() => setShow(false)}
      >
        {symbol}
      </span>
      {show && func && (
        <div className="absolute left-0 top-full mt-1 z-50 w-72 bg-card border border-border rounded-lg shadow-xl p-3 text-xs text-card-foreground">
          <p className="font-semibold text-foreground mb-1">{func.protein_name}</p>
          <p className="text-muted-foreground leading-relaxed line-clamp-5">{func.function}</p>
          <a href={func.uniprot_url} target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-1 mt-1.5 text-blue-600 dark:text-blue-400 hover:underline">
            <ExternalIcon />
            UniProt {func.accession}
          </a>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main card component
// ---------------------------------------------------------------------------

/** Returns a direction badge for SE exon-skipping events based on ΔΨ sign.
 *  Always names the group that has MORE skipping so the label reads
 *  "↑ Exon skipping in patients" (en) / "↑ Saut chez patients" (fr).
 */
function SEDirectionBadge({
  delta,
  group1Label = "Group 1",
  group2Label = "Group 2",
  eventType,
  t,
}: {
  delta: number | null | undefined;
  group1Label?: string;
  group2Label?: string;
  eventType: string | null | undefined;
  t: (key: string, vars?: Record<string, string | number>) => string;
}) {
  if (eventType !== "SE" || delta === null || delta === undefined || delta === 0) return null;
  const moreSkippingLabel = delta < 0 ? group1Label : group2Label;
  // ΔΨ < 0 → more skipping in group 1 (patients) → RED
  // ΔΨ > 0 → more skipping in group 2 (controls) → BLUE
  const colorClasses = delta < 0
    ? "text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-950/40 border-red-200 dark:border-red-800"
    : "text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-950/40 border-blue-200 dark:border-blue-800";
  return (
    <span className={`inline-flex items-center gap-0.5 text-[10px] font-semibold border ${colorClasses} px-1.5 py-0.5 rounded-md whitespace-nowrap leading-none`}>
      {t("annotatedCard.direction.skippingUp", { group: moreSkippingLabel })}
    </span>
  );
}

export function AnnotatedCard({ event: ev, mode, ensemblIdHint, mutatedGenes, analysisId, group1Label, group2Label, rank }: AnnotatedCardProps) {
  const t = useT();
  const symbol = ev.gene_symbol ?? ev.gene_id ?? "";

  // annotation always fetched when symbol available (needed for PanelApp badge + GO + gene views)
  const needsAnnotation = !!symbol;
  const { data: annotation, isLoading: annotationLoading } = useQuery({
    queryKey: ["annotation", symbol, ensemblIdHint],
    queryFn: () => getGeneAnnotation(symbol, ensemblIdHint),
    enabled: !!symbol && needsAnnotation,
    staleTime: 5 * 60 * 1000,
  });

  // Mode splice : compact header + on-demand diagram (click to expand)
  const [spliceExpanded, setSpliceExpanded] = useState(false);

  if (mode === "splice") {
    return (
      <div className="flex flex-col border border-border dark:border-slate-600 rounded-xl bg-card dark:bg-slate-800/80 shadow-sm">
        {/* Header compact inline */}
        <div className="flex items-center gap-2 px-3 py-2 border-b border-border dark:border-slate-600/60">
          <span className="w-5 h-5 flex items-center justify-center rounded-full bg-blue-600 text-white text-[10px] font-bold shrink-0">
            {rank ?? "·"}
          </span>
          <GeneSymbolWithTooltip symbol={symbol || "—"} annotation={annotation} />
          <div className="flex items-center gap-1.5 ml-auto shrink-0 flex-wrap">
            <PanelAppBadge annotation={annotation} />
            <EventTypeBadge type={ev.event_type} />
            <span className="text-[10px] text-muted-foreground font-mono">
              FDR {formatFDR(ev.fdr)}
            </span>
            <span className={`text-[10px] font-bold font-mono ${
              (ev.inc_level_difference ?? 0) < 0
                ? "text-red-500 dark:text-red-400"
                : "text-blue-500 dark:text-blue-400"
            }`}>
              ΔΨ {formatDeltaPSI(ev.inc_level_difference)}
            </span>
            <SEDirectionBadge
              delta={ev.inc_level_difference}
              eventType={ev.event_type}
              group1Label={group1Label}
              group2Label={group2Label}
              t={t}
            />
            {/* Toggle diagram button */}
            <button
              onClick={() => setSpliceExpanded((v) => !v)}
              className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-semibold rounded-md border transition-colors ${
                spliceExpanded
                  ? "bg-blue-600 text-white border-blue-600"
                  : "border-border text-muted-foreground hover:text-foreground hover:bg-muted"
              }`}
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d={spliceExpanded ? "M19 9l-7 7-7-7" : "M9 5l7 7-7 7"} />
              </svg>
              {spliceExpanded ? t("annotatedCard.splice.hideDiagram") : t("annotatedCard.splice.showDiagram")}
            </button>
          </div>
        </div>
        {/* Diagram loaded on demand only */}
        {spliceExpanded && (
          <div className="px-2 py-3">
            <SpliceView event={ev} analysisId={analysisId} group1Label={group1Label} group2Label={group2Label} />
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col border border-border dark:border-slate-600 rounded-xl bg-card dark:bg-slate-800/80 shadow-sm hover:shadow-md transition-shadow">
      {/* ── Fixed header ── */}
      <div className="flex items-start justify-between gap-2 p-4 pb-3 border-b border-border dark:border-slate-600/60">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="w-7 h-7 flex items-center justify-center rounded-full bg-blue-600 text-white text-xs font-bold shrink-0">
            {rank ?? "·"}
          </span>
          <GeneSymbolWithTooltip symbol={symbol || "—"} annotation={annotation} />
        </div>
        {/* Right side: EventType badge + PanelApp badge */}
        <div className="flex items-center gap-1.5 shrink-0">
          <PanelAppBadge annotation={annotation} />
          <EventTypeBadge type={ev.event_type} />
        </div>
      </div>

      {/* ── Quick stats ── */}
      <div className="flex flex-wrap items-center gap-4 px-4 py-2 border-b border-border dark:border-slate-600/60 bg-muted/20 dark:bg-slate-700/30">
        <div>
          <dt className="text-[10px] text-muted-foreground">FDR</dt>
          <dd className="text-xs font-bold text-foreground">{formatFDR(ev.fdr)}</dd>
        </div>
        <div>
          <dt className="text-[10px] text-muted-foreground">ΔPSI</dt>
          <dd className={`text-xs font-bold ${
            (ev.inc_level_difference ?? 0) < 0
              ? "text-red-600 dark:text-red-400"
              : "text-blue-600 dark:text-blue-400"
          }`}>
            {formatDeltaPSI(ev.inc_level_difference)}
          </dd>
        </div>
        <div>
          <dt className="text-[10px] text-muted-foreground">|ΔPSI|</dt>
          <dd className="text-xs font-semibold text-foreground">{ev.abs_inc_level_diff?.toFixed(3) ?? "—"}</dd>
        </div>
        <SEDirectionBadge
          delta={ev.inc_level_difference}
          eventType={ev.event_type}
          group1Label={group1Label}
          group2Label={group2Label}
          t={t}
        />
      </div>

      {/* ── Dynamic content ── */}
      <div className="p-4 flex-1">
        {mode === "gene" && (
          <div className="space-y-4">
            <GeneView ev={ev} annotation={annotation} />
            <GOView annotation={annotation} isLoading={annotationLoading} />
            {annotation?.panels && annotation.panels.length > 0 && (
              <PanelAppView annotation={annotation} isLoading={annotationLoading} />
            )}
          </div>
        )}
        {mode === "stringdb" && <StringDBView eventSymbol={symbol} mutatedGenes={mutatedGenes} />}
        {(mode === "pathways" || mode === "motifs") && (
          <ComingSoonView mode={mode} />
        )}
      </div>
    </div>
  );
}
