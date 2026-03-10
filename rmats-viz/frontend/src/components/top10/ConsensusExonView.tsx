"use client";

/**
 * ConsensusExonView
 * ==================
 * "Figure principale" — ExonDiagram de l'exon fictif consensus construit
 * depuis les statistiques agrégées de tous les événements SE de l'analyse.
 *
 * Paramètres utilisés depuis PatternAnalysisResponse :
 *  • exon_sizes.mean         → taille de l'exon fictif
 *  • upstream_intron_sizes.median / downstream_intron_sizes.median
 *                            → tailles des introns flanquants
 *  • mean_delta_psi          → ΔΨ moyen (épaisseur + couleur de l'arc)
 *  • donor_sites.consensus   → séquence consensus 5'SS (9 nt)
 *  • acceptor_sites.consensus → séquence consensus 3'SS (23 nt)
 *  • ppt.mean_score          → score PPT moyen
 *
 * Réutilise ExonDiagram sans aucune modification.
 */

import { ExonDiagram } from "./ExonDiagram";
import { useT } from "@/contexts/LanguageContext";
import type { PatternAnalysisResponse } from "@/types/splice";

interface ConsensusExonViewProps {
  data: PatternAnalysisResponse;
}

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function StatChip({ label, value }: { label: string; value: string | number | null }) {
  if (value === null || value === undefined) return null;
  return (
    <div className="flex flex-col items-center px-3 py-2 rounded-lg bg-muted/40 border border-border text-center min-w-[70px]">
      <span className="text-[9px] text-muted-foreground uppercase tracking-wide">{label}</span>
      <span className="text-sm font-bold text-foreground tabular-nums">{value}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ConsensusExonView({ data }: ConsensusExonViewProps) {
  const t = useT();
  const {
    n_se_events,
    n_analyzed,
    exon_sizes,
    upstream_intron_sizes,
    downstream_intron_sizes,
    mean_delta_psi,
    donor_sites,
    acceptor_sites,
    ppt,
    frame,
    fasta_available,
  } = data;

  const hasConsensus = fasta_available && donor_sites.consensus && acceptor_sites.consensus;

  // Build a pseudo-FDR for the arc display — use pct_canonical as a proxy
  // Map combined canonical percentage to a "significance" score:
  // 100% canonical → pseudo-FDR 0.001 (very dark arc)
  // 50% canonical  → pseudo-FDR 0.5 (light arc)
  const meanCanonical = hasConsensus
    ? (donor_sites.pct_canonical + acceptor_sites.pct_canonical) / 2
    : 0;
  const pseudoFdr = hasConsensus
    ? Math.max(0.001, 1 - meanCanonical / 100)
    : null;

  return (
    <div className="space-y-4">

      {/* ── Header stats ── */}
      <div className="flex flex-wrap gap-2">
        <StatChip label={t("consensusExon.seEvents")} value={n_se_events} />
        <StatChip label={t("consensusExon.analyzed")} value={n_analyzed} />
        {exon_sizes.mean !== null && (
          <StatChip label={t("consensusExon.meanExon")} value={`${Math.round(exon_sizes.mean)} nt`} />
        )}
        {upstream_intron_sizes.median !== null && (
          <StatChip label={t("consensusExon.upstreamMedian")} value={`${Math.round(upstream_intron_sizes.median)} nt`} />
        )}
        {downstream_intron_sizes.median !== null && (
          <StatChip label={t("consensusExon.downstreamMedian")} value={`${Math.round(downstream_intron_sizes.median)} nt`} />
        )}
        {mean_delta_psi !== null && (
          <StatChip
            label={t("consensusExon.meanDeltaPsi")}
            value={mean_delta_psi >= 0 ? `+${mean_delta_psi.toFixed(2)}` : mean_delta_psi.toFixed(2)}
          />
        )}
        {ppt.mean_score !== null && (
          <StatChip label={t("consensusExon.meanPpt")} value={`${Math.round(ppt.mean_score * 100)}%`} />
        )}
      </div>

      {/* ── Consensus diagram ── */}
      <div>
        <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-2">
          {t("consensusExon.consensusExonLabel")}
          {!hasConsensus && (
            <span className="ml-2 text-amber-600 dark:text-amber-400 normal-case">
              {t("consensusExon.noSeq")}
            </span>
          )}
        </p>

        <ExonDiagram
          exonSize={exon_sizes.mean !== null ? Math.round(exon_sizes.mean) : null}
          upstreamIntronSize={upstream_intron_sizes.median !== null ? Math.round(upstream_intron_sizes.median) : null}
          downstreamIntronSize={downstream_intron_sizes.median !== null ? Math.round(downstream_intron_sizes.median) : null}
          incLevelDifference={mean_delta_psi}
          fdr={pseudoFdr}
          pValue={null}
          strand={null}
          donorIsGt={hasConsensus ? donor_sites.pct_canonical >= 80 : null}
          acceptorIsAg={hasConsensus ? acceptor_sites.pct_canonical >= 80 : null}
          donorSeq={hasConsensus ? donor_sites.consensus ?? null : null}
          acceptorSeq={hasConsensus ? acceptor_sites.consensus ?? null : null}
          pptScore={ppt.mean_score}
          frameClass={
            frame.in_frame > frame.frameshift + frame.non_coding
              ? "in_frame"
              : frame.frameshift > frame.non_coding
              ? "frameshift"
              : "non_coding"
          }
        />
      </div>

      {/* ── Frame breakdown summary ── */}
      <div className="flex flex-wrap gap-3 text-[10px]">
        {[
          { label: "In-frame",                               val: frame.in_frame,   color: "text-green-600 dark:text-green-400" },
          { label: "Frameshift",                             val: frame.frameshift,  color: "text-red-600 dark:text-red-400" },
          { label: t("consensusExon.frameLabelNonCoding"),   val: frame.non_coding,  color: "text-slate-500" },
        ].map((f) => (
          <span key={f.label} className={`${f.color} font-semibold`}>
            {f.label} : <span className="tabular-nums">{f.val}</span>
          </span>
        ))}
        {exon_sizes.min !== null && exon_sizes.max !== null && (
          <span className="text-muted-foreground">
            {t("consensusExon.sizeRange", { min: exon_sizes.min!, max: exon_sizes.max! })}
          </span>
        )}
      </div>

      <p className="text-[9px] text-muted-foreground italic">
        {t("consensusExon.description", { n: n_se_events })}
      </p>
    </div>
  );
}
