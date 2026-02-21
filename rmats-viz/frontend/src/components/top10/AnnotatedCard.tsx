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
import { getGeneAnnotation } from "@/lib/api/annotations";
import { EventTypeBadge } from "@/components/events/EventTypeBadge";
import { formatFDR, formatDeltaPSI, formatCoord } from "@/lib/utils";
import type { SplicingEvent } from "@/types/event";
import type { GeneAnnotation, PanelConfidence } from "@/types/annotation";
import type { GeneEntry } from "@/types/gene";
import type { ViewMode } from "./types";

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

const GO_CATEGORY_LABELS: Record<string, string> = {
  BP: "Processus biologique",
  MF: "Fonction moléculaire",
  CC: "Composant cellulaire",
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
  const ensgId = annotation?.ensembl_id ?? ev.gene_id ?? null;
  const ensemblLink = ensgId
    ? `https://www.ensembl.org/Homo_sapiens/Gene/Summary?g=${ensgId}`
    : null;

  return (
    <div className="space-y-2 text-sm">
      {ensgId && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-muted-foreground text-xs">ENSG :</span>
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
      <div className="text-xs text-muted-foreground bg-muted/40 rounded px-3 py-2 space-y-0.5">
        <div><span className="font-medium text-foreground">Chr :</span>{" "}{ev.chr ?? "?"} {ev.strand ? `(brin ${ev.strand})` : ""}</div>
        <div><span className="font-medium text-foreground">Exon :</span>{" "}{formatCoord(ev.exon_start)} – {formatCoord(ev.exon_end)}</div>
        <div><span className="font-medium text-foreground">Upstream :</span>{" "}{formatCoord(ev.upstream_es)} – {formatCoord(ev.upstream_ee)}</div>
        <div><span className="font-medium text-foreground">Downstream :</span>{" "}{formatCoord(ev.downstream_es)} – {formatCoord(ev.downstream_ee)}</div>
      </div>
      {ensemblLink && (
        <a href={ensemblLink} target="_blank" rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline">
          <ExternalIcon />
          Voir sur Ensembl
        </a>
      )}
    </div>
  );
}

function GOView({ annotation, isLoading }: { annotation?: GeneAnnotation; isLoading: boolean }) {
  if (isLoading) {
    return <div className="space-y-2">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-6 w-full" />)}</div>;
  }
  const terms = annotation?.go_terms ?? [];
  if (terms.length === 0) {
    return <p className="text-xs text-muted-foreground italic">Aucun terme GO disponible.</p>;
  }
  const grouped = terms.reduce<Record<string, typeof terms>>((acc, t) => {
    if (!acc[t.category]) acc[t.category] = [];
    acc[t.category].push(t);
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
              {GO_CATEGORY_LABELS[cat]}
            </p>
            <div className="flex flex-wrap gap-1">
              {catTerms.slice(0, 4).map((t) => (
                <a key={t.id} href={`https://www.ebi.ac.uk/QuickGO/term/${t.id}`}
                  target="_blank" rel="noopener noreferrer"
                  title={`${t.id} · Evidence: ${t.evidence || "–"}`}
                  className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] border font-medium hover:opacity-80 transition-opacity ${GO_CATEGORY_COLOR[cat] ?? "bg-muted text-foreground"}`}>
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

function PanelAppView({ annotation, isLoading }: { annotation?: GeneAnnotation; isLoading: boolean }) {
  if (isLoading) {
    return <div className="space-y-2">{[1, 2].map((i) => <Skeleton key={i} className="h-8 w-full" />)}</div>;
  }
  const panels = annotation?.panels ?? [];
  if (panels.length === 0) {
    return <p className="text-xs text-muted-foreground italic">Aucun panel PanelApp trouvé.</p>;
  }
  return (
    <div className="space-y-1.5">
      {panels.slice(0, 4).map((p) => {
        const conf = p.confidence_label as PanelConfidence;
        return (
          <div key={p.panel_name}
            className={`flex items-start gap-2 px-2.5 py-2 rounded-lg border text-xs ${CONFIDENCE_STYLES[conf]}`}>
            <span className={`mt-0.5 w-2 h-2 rounded-full shrink-0 ${CONFIDENCE_DOT[conf]}`} />
            <div className="min-w-0">
              <p className="font-semibold leading-tight">{p.panel_name}</p>
              {p.disorders.length > 0 && (
                <p className="text-[11px] opacity-75 mt-0.5 truncate">
                  {p.disorders.slice(0, 2).join(", ")}
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
        Voir sur PanelApp AU
      </a>
    </div>
  );
}

function ScoresView({ ev }: { ev: SplicingEvent }) {
  const incL1 = ev.inc_level_1?.split(",").map(Number).filter((v) => !isNaN(v)) ?? [];
  const incL2 = ev.inc_level_2?.split(",").map(Number).filter((v) => !isNaN(v)) ?? [];
  const mean = (arr: number[]) =>
    arr.length ? (arr.reduce((a, b) => a + b, 0) / arr.length).toFixed(3) : "—";

  return (
    <div className="space-y-2 text-xs">
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
        <StatRow label="FDR" value={formatFDR(ev.fdr)} highlight />
        <StatRow label="p-value" value={ev.p_value != null ? ev.p_value.toExponential(2) : "—"} />
        <StatRow label="ΔPSI" value={formatDeltaPSI(ev.inc_level_difference)} highlight />
        <StatRow label="|ΔPSI|" value={ev.abs_inc_level_diff?.toFixed(3) ?? "—"} />
        <StatRow label="PSI moy. G1" value={mean(incL1)} />
        <StatRow label="PSI moy. G2" value={mean(incL2)} />
      </div>
      <div className="bg-muted/40 rounded px-2.5 py-2 space-y-1">
        <p className="font-semibold text-foreground text-[10px] uppercase tracking-wide mb-1">
          Comptages (3 premiers échantillons)
        </p>
        {ev.ijc_sample_1 && <p><span className="text-muted-foreground">IJC G1:</span>{" "}{ev.ijc_sample_1.split(",").slice(0, 3).join(", ")}{ev.ijc_sample_1.split(",").length > 3 ? "…" : ""}</p>}
        {ev.sjc_sample_1 && <p><span className="text-muted-foreground">SJC G1:</span>{" "}{ev.sjc_sample_1.split(",").slice(0, 3).join(", ")}{ev.sjc_sample_1.split(",").length > 3 ? "…" : ""}</p>}
        {ev.ijc_sample_2 && <p><span className="text-muted-foreground">IJC G2:</span>{" "}{ev.ijc_sample_2.split(",").slice(0, 3).join(", ")}{ev.ijc_sample_2.split(",").length > 3 ? "…" : ""}</p>}
        {ev.sjc_sample_2 && <p><span className="text-muted-foreground">SJC G2:</span>{" "}{ev.sjc_sample_2.split(",").slice(0, 3).join(", ")}{ev.sjc_sample_2.split(",").length > 3 ? "…" : ""}</p>}
      </div>
    </div>
  );
}

/**
 * StringDBView
 * Shows the STRING protein interaction network between each mutated gene
 * and the current event gene.
 * Uses the STRING API image endpoint directly (no CORS issues, public API).
 *
 * STRING API docs: https://string-db.org/help/api/
 * Image endpoint: GET /api/image/network?identifiers={A}%0D{B}&species=9606
 */
function StringDBView({
  eventSymbol,
  mutatedGenes,
}: {
  eventSymbol: string;
  mutatedGenes: GeneEntry[];
}) {
  const [imgErrors, setImgErrors] = useState<Record<string, boolean>>({});

  if (!eventSymbol) {
    return <p className="text-xs text-muted-foreground italic">Symbole du gène non disponible.</p>;
  }

  return (
    <div className="space-y-3">
      {mutatedGenes.map((mutGene) => {
        const isSelf = mutGene.symbol.toUpperCase() === eventSymbol.toUpperCase();
        // STRING uses %0D (carriage-return) as separator between gene identifiers
        const identifiers = isSelf
          ? encodeURIComponent(eventSymbol)
          : `${encodeURIComponent(mutGene.symbol)}%0D${encodeURIComponent(eventSymbol)}`;

        const imgUrl = `https://string-db.org/api/image/network?identifiers=${identifiers}&species=9606&network_flavor=evidence&caller_identity=rmats-viz`;
        const pageUrl = `https://string-db.org/cgi/network?identifiers=${identifiers}&species=9606`;

        const hasError = imgErrors[mutGene.symbol];

        return (
          <div key={mutGene.symbol} className="space-y-1.5">
            {/* Pair label */}
            <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
              <span className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300 border border-amber-200 dark:border-amber-700">
                {mutGene.symbol}
              </span>
              {!isSelf && (
                <>
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                  </svg>
                  <span className="px-1.5 py-0.5 rounded bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300 border border-blue-200 dark:border-blue-700">
                    {eventSymbol}
                  </span>
                </>
              )}
            </div>

            {/* Network image */}
            {hasError ? (
              <p className="text-[11px] text-muted-foreground italic">
                Image STRING non disponible pour cette paire.
              </p>
            ) : (
              <a href={pageUrl} target="_blank" rel="noopener noreferrer" title="Ouvrir dans STRING-DB">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={imgUrl}
                  alt={`Réseau STRING : ${mutGene.symbol} – ${eventSymbol}`}
                  className="w-full rounded-lg border border-border hover:opacity-90 transition-opacity"
                  onError={() => setImgErrors((prev) => ({ ...prev, [mutGene.symbol]: true }))}
                />
              </a>
            )}

            <a href={pageUrl} target="_blank" rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-[11px] text-blue-600 dark:text-blue-400 hover:underline">
              <ExternalIcon />
              Ouvrir dans STRING-DB
            </a>
          </div>
        );
      })}
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

export function AnnotatedCard({ event: ev, mode, ensemblIdHint, mutatedGenes }: AnnotatedCardProps) {
  const symbol = ev.gene_symbol ?? ev.gene_id ?? "";

  const needsAnnotation = mode === "go" || mode === "panelapp" || !!symbol;
  const { data: annotation, isLoading: annotationLoading } = useQuery({
    queryKey: ["annotation", symbol, ensemblIdHint],
    queryFn: () => getGeneAnnotation(symbol, ensemblIdHint),
    enabled: !!symbol && needsAnnotation,
    staleTime: 5 * 60 * 1000,
  });

  return (
    <div className="flex flex-col border border-border rounded-xl bg-card shadow-sm hover:shadow-md transition-shadow">
      {/* ── Fixed header ── */}
      <div className="flex items-start justify-between gap-2 p-4 pb-3 border-b border-border">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="w-7 h-7 flex items-center justify-center rounded-full bg-blue-600 text-white text-xs font-bold shrink-0">
            {ev.top_rank}
          </span>
          <GeneSymbolWithTooltip symbol={symbol || "—"} annotation={annotation} />
        </div>
        <EventTypeBadge type={ev.event_type} />
      </div>

      {/* ── Quick stats ── */}
      <div className="flex gap-4 px-4 py-2 border-b border-border bg-muted/20">
        <div>
          <dt className="text-[10px] text-muted-foreground">FDR</dt>
          <dd className="text-xs font-bold text-foreground">{formatFDR(ev.fdr)}</dd>
        </div>
        <div>
          <dt className="text-[10px] text-muted-foreground">ΔPSI</dt>
          <dd className={`text-xs font-bold ${
            (ev.inc_level_difference ?? 0) > 0
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
      </div>

      {/* ── Dynamic content ── */}
      <div className="p-4 flex-1">
        {mode === "gene"     && <GeneView ev={ev} annotation={annotation} />}
        {mode === "go"       && <GOView annotation={annotation} isLoading={annotationLoading} />}
        {mode === "panelapp" && <PanelAppView annotation={annotation} isLoading={annotationLoading} />}
        {mode === "scores"   && <ScoresView ev={ev} />}
        {mode === "stringdb" && (
          <StringDBView eventSymbol={symbol} mutatedGenes={mutatedGenes} />
        )}
      </div>
    </div>
  );
}
