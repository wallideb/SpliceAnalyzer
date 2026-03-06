"use client";

/**
 * MotifPatternPanel
 * ==================
 * Aggregate splice-signal analysis panel — displayed in the main content area
 * when the user selects the "Motifs récurrents" sidebar tab in the deep-analysis
 * view (mode === "motifs").
 *
 * Shows:
 *  - Summary: n SE events analysed, n canonical clusters
 *  - Exon size histogram (SVG bar chart, bins of 25 nt)
 *  - 5'SS donor sequence logo (9 nt around GT)
 *  - 3'SS acceptor sequence logo (23 nt around AG)
 *  - PPT score distribution (score bar list)
 *  - Frame breakdown bar (in_frame / frameshift / non_coding / unknown)
 *  - Branch-point detection rate
 *
 * Data is fetched from GET /api/v1/splice/patterns/{analysisId}.
 * A "Calculer" button triggers POST /api/v1/splice/compute/{analysisId}.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getSplicePatterns, computeSpliceFeatures } from "@/lib/api/splice";
import type { SplicingEvent } from "@/types/event";
import { SpliceSequenceLogo } from "./SpliceSequenceLogo";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface MotifPatternPanelProps {
  events: SplicingEvent[];
  analysisId: string;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Thin horizontal progress bar. */
function Bar({ pct, className = "" }: { pct: number; className?: string }) {
  return (
    <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
      <div
        className={`h-full rounded-full ${className}`}
        style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
      />
    </div>
  );
}

/** SVG exon-size histogram from bin→count pairs. */
function ExonSizeHistogram({
  distribution,
}: {
  distribution: { bin: number; count: number }[];
}) {
  if (!distribution.length) return null;

  const W = 340, H = 80;
  const maxCount = Math.max(...distribution.map((d) => d.count), 1);
  const barW = Math.max(4, Math.floor(W / distribution.length) - 1);

  return (
    <svg
      viewBox={`0 0 ${W} ${H + 16}`}
      className="w-full max-w-[340px]"
      aria-label="Distribution des tailles d'exons sautés"
    >
      {distribution.map((d, i) => {
        const barH = Math.round((d.count / maxCount) * H);
        const x = i * (barW + 1);
        const y = H - barH;
        return (
          <g key={d.bin}>
            <rect x={x} y={y} width={barW} height={barH} className="fill-blue-500/70" rx={1} />
            {/* x-axis label every 5 bins */}
            {i % 5 === 0 && (
              <text
                x={x + barW / 2}
                y={H + 12}
                textAnchor="middle"
                fontSize={7}
                className="fill-muted-foreground"
              >
                {d.bin}
              </text>
            )}
          </g>
        );
      })}
      {/* x-axis line */}
      <line x1={0} y1={H} x2={W} y2={H} strokeWidth={0.5} className="stroke-border" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function MotifPatternPanel({ events, analysisId }: MotifPatternPanelProps) {
  const qc = useQueryClient();

  const seCount = events.filter((e) => e.event_type === "SE").length;

  const { data, isLoading, isError } = useQuery({
    queryKey: ["splice-patterns", analysisId],
    queryFn: () => getSplicePatterns(analysisId),
    enabled: !!analysisId,
    staleTime: 10 * 60 * 1000,
    retry: false,
  });

  const compute = useMutation({
    mutationFn: () => computeSpliceFeatures(analysisId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["splice-patterns", analysisId] }),
  });

  // ── Loading ──────────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="space-y-3 p-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-6 rounded bg-muted animate-pulse" />
        ))}
      </div>
    );
  }

  // ── Not computed / error ─────────────────────────────────────────────────
  if (isError || !data) {
    return (
      <div className="flex flex-col items-center gap-4 py-10 text-center">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="w-10 h-10 text-muted-foreground/40"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1.5}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
        </svg>
        <div>
          <p className="text-sm font-semibold text-foreground mb-1">
            Analyse de patterns non calculée
          </p>
          <p className="text-xs text-muted-foreground max-w-xs leading-relaxed">
            Calculez les features d&apos;épissage pour les {seCount} événements SE de cette analyse
            afin de visualiser les patterns récurrents (sites GT-AG, PPT, point de branchement,
            classe de cadre de lecture).
          </p>
        </div>
        <button
          onClick={() => compute.mutate()}
          disabled={compute.isPending}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-semibold bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50 transition-colors"
        >
          {compute.isPending && (
            <svg className="animate-spin w-4 h-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          )}
          {compute.isPending ? "Calcul en cours…" : "Calculer les features"}
        </button>
        {compute.isError && (
          <p className="text-xs text-red-500">Erreur lors du calcul. Réessayez.</p>
        )}
      </div>
    );
  }

  // ── Computed ─────────────────────────────────────────────────────────────
  const { exon_sizes, donor_sites, acceptor_sites, ppt, frame, bp_found_pct } = data;

  // Frame totals for bar widths
  const frameTotal = (frame.in_frame + frame.frameshift + frame.non_coding + frame.unknown) || 1;
  const frameBars = [
    { label: "In-frame",   value: frame.in_frame,   pct: (frame.in_frame / frameTotal) * 100,   color: "bg-green-500" },
    { label: "Frameshift", value: frame.frameshift,  pct: (frame.frameshift / frameTotal) * 100,  color: "bg-red-500" },
    { label: "Non-codant", value: frame.non_coding,  pct: (frame.non_coding / frameTotal) * 100,  color: "bg-slate-400" },
    { label: "Inconnu",    value: frame.unknown,     pct: (frame.unknown / frameTotal) * 100,     color: "bg-muted-foreground/30" },
  ];

  return (
    <div className="space-y-6 text-xs">

      {/* ── Summary header ── */}
      <div className="flex flex-wrap gap-4">
        <SummaryChip label="Événements SE" value={data.n_se_events} />
        <SummaryChip label="Analysés (seq.)" value={data.n_analyzed} />
        <SummaryChip label="Clusters" value={data.clusters.n_clusters} />
        {!data.fasta_available && (
          <span className="self-center text-[10px] text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded px-2 py-1">
            FASTA non disponible — tailles depuis coords uniquement
          </span>
        )}
      </div>

      {/* ── Exon size distribution ── */}
      {exon_sizes && (
        <Section title="Distribution des tailles d'exons sautés (nt)">
          {exon_sizes.mean !== null && (
            <div className="flex gap-4 mb-2 text-[10px] text-muted-foreground">
              <span>Moy. <strong className="text-foreground">{exon_sizes.mean} nt</strong></span>
              <span>Méd. <strong className="text-foreground">{exon_sizes.median} nt</strong></span>
              <span>Min <strong className="text-foreground">{exon_sizes.min}</strong></span>
              <span>Max <strong className="text-foreground">{exon_sizes.max}</strong></span>
            </div>
          )}
          <ExonSizeHistogram distribution={exon_sizes.distribution} />
        </Section>
      )}

      {/* ── 5'SS donor logo ── */}
      {donor_sites && donor_sites.pwm.length > 0 && (
        <Section title={`Site donneur 5'SS — ${donor_sites.n_sequences} séquences · ${donor_sites.pct_canonical}% GT canonique`}>
          {donor_sites.consensus && (
            <p className="text-[10px] text-muted-foreground mb-1">
              Consensus IUPAC : <code className="font-mono font-bold text-foreground">{donor_sites.consensus}</code>
            </p>
          )}
          <SpliceSequenceLogo pwm={donor_sites.pwm} highlight={[3, 4]} />
        </Section>
      )}

      {/* ── 3'SS acceptor logo ── */}
      {acceptor_sites && acceptor_sites.pwm.length > 0 && (
        <Section title={`Site accepteur 3'SS — ${acceptor_sites.n_sequences} séquences · ${acceptor_sites.pct_canonical}% AG canonique`}>
          {acceptor_sites.consensus && (
            <p className="text-[10px] text-muted-foreground mb-1">
              Consensus IUPAC : <code className="font-mono font-bold text-foreground">{acceptor_sites.consensus}</code>
            </p>
          )}
          <SpliceSequenceLogo pwm={acceptor_sites.pwm} highlight={[17, 18]} />
        </Section>
      )}

      {/* ── PPT score distribution ── */}
      {ppt && ppt.scores.length > 0 && (
        <Section title={`Zone PPT — score moyen ${ppt.mean_score !== null ? Math.round(ppt.mean_score * 100) + "%" : "—"} · run Y le plus long : ${ppt.mean_longest_run ?? "—"} nt`}>
          <div className="flex flex-wrap gap-1 max-h-24 overflow-y-auto">
            {ppt.scores.slice(0, 50).map((s, i) => (
              <div key={i} className="flex items-center gap-1 w-14">
                <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full rounded-full bg-amber-400"
                    style={{ width: `${Math.round(s * 100)}%` }}
                  />
                </div>
                <span className="text-[9px] tabular-nums text-muted-foreground w-5 text-right">
                  {Math.round(s * 100)}
                </span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* ── Frame breakdown ── */}
      <Section title="Classe de cadre de lecture (exon sauté)">
        <div className="space-y-1.5">
          {frameBars.map((fb) => (
            <div key={fb.label} className="flex items-center gap-2">
              <span className="w-20 text-[10px] text-muted-foreground truncate">{fb.label}</span>
              <Bar pct={fb.pct} className={fb.color} />
              <span className="w-8 text-right text-[10px] font-semibold tabular-nums text-foreground">
                {fb.value}
              </span>
            </div>
          ))}
        </div>
      </Section>

      {/* ── Branch-point ── */}
      {bp_found_pct !== null && (
        <Section title="Détection du point de branchement (motif YNYURAY)">
          <div className="flex items-center gap-3">
            <Bar pct={bp_found_pct} className="bg-green-500" />
            <span className="text-[11px] font-semibold text-foreground tabular-nums">
              {bp_found_pct}%
            </span>
            <span className="text-[10px] text-muted-foreground">trouvés</span>
          </div>
        </Section>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mini helpers
// ---------------------------------------------------------------------------

function SummaryChip({ label, value }: { label: string; value: number }) {
  return (
    <div className="text-center px-3 py-2 rounded-lg bg-muted/40 border border-border">
      <p className="text-[9px] text-muted-foreground uppercase tracking-wide">{label}</p>
      <p className="text-base font-bold text-foreground tabular-nums">{value}</p>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-2">
        {title}
      </p>
      {children}
    </div>
  );
}
