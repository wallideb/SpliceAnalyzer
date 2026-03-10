"use client";

/**
 * PatternComparisonPanel
 * =======================
 * Side-by-side comparison of splice pattern statistics
 * between significant and non-significant event groups.
 */

import { useQuery } from "@tanstack/react-query";
import { getPatternComparison } from "@/lib/api/deep-analyses";
import type { GroupPatternStats } from "@/lib/api/deep-analyses";
import { useT } from "@/contexts/LanguageContext";

interface Props {
  deepId: string;
}

function StatRow({
  label,
  sigVal,
  nonsigVal,
  format = "default",
}: {
  label: string;
  sigVal: string | number | null;
  nonsigVal: string | number | null;
  format?: "default" | "pct" | "count";
}) {
  const fmt = (v: string | number | null) => {
    if (v === null || v === undefined) return "—";
    if (format === "pct" && typeof v === "number") return `${v}%`;
    if (typeof v === "number") return v.toLocaleString();
    return v;
  };

  return (
    <tr className="border-b border-border/50">
      <td className="px-3 py-2 text-xs text-muted-foreground font-medium">{label}</td>
      <td className="px-3 py-2 text-xs text-foreground font-semibold tabular-nums text-center">
        {fmt(sigVal)}
      </td>
      <td className="px-3 py-2 text-xs text-muted-foreground tabular-nums text-center">
        {fmt(nonsigVal)}
      </td>
    </tr>
  );
}

function GroupHeader({ label, n, color }: { label: string; n: number; color: string }) {
  return (
    <th className={`px-3 py-2.5 text-xs font-bold text-center ${color}`}>
      {label}
      <span className="ml-1 font-normal opacity-70">({n})</span>
    </th>
  );
}

export function PatternComparisonPanel({ deepId }: Props) {
  const t = useT();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["pattern-comparison", deepId],
    queryFn: () => getPatternComparison(deepId),
    enabled: !!deepId,
    staleTime: 5 * 60 * 1000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-muted-foreground text-sm py-4">
        <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        {t("deepAnalysis.loading")}
      </div>
    );
  }

  if (isError || !data) {
    return (
      <p className="text-xs text-muted-foreground py-4">
        Pattern comparison not available. Ensure splice features have been computed.
      </p>
    );
  }

  const { significant: sig, not_significant: nonsig } = data;

  return (
    <div className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 border-b border-border">
          <tr>
            <th className="px-3 py-2.5 text-xs font-semibold text-left text-muted-foreground w-1/3">
              Feature
            </th>
            <GroupHeader
              label={t("deepAnalysis.significant")}
              n={sig.n_events}
              color="text-green-700 dark:text-green-400"
            />
            <GroupHeader
              label={t("deepAnalysis.notSignificant")}
              n={nonsig.n_events}
              color="text-slate-500"
            />
          </tr>
        </thead>
        <tbody>
          <StatRow label="SE events with features" sigVal={sig.n_se_with_features} nonsigVal={nonsig.n_se_with_features} />
          <StatRow label="Mean exon size" sigVal={sig.exon_size_mean != null ? `${sig.exon_size_mean} nt` : null} nonsigVal={nonsig.exon_size_mean != null ? `${nonsig.exon_size_mean} nt` : null} />
          <StatRow label="Median exon size" sigVal={sig.exon_size_median != null ? `${sig.exon_size_median} nt` : null} nonsigVal={nonsig.exon_size_median != null ? `${nonsig.exon_size_median} nt` : null} />
          <StatRow label="Canonical GT (5'SS)" sigVal={sig.pct_canonical_gt} nonsigVal={nonsig.pct_canonical_gt} format="pct" />
          <StatRow label="Canonical AG (3'SS)" sigVal={sig.pct_canonical_ag} nonsigVal={nonsig.pct_canonical_ag} format="pct" />
          <StatRow label="Mean PPT score" sigVal={sig.ppt_mean_score != null ? `${Math.round(sig.ppt_mean_score * 100)}%` : null} nonsigVal={nonsig.ppt_mean_score != null ? `${Math.round(nonsig.ppt_mean_score * 100)}%` : null} />
          <StatRow label="In-frame" sigVal={sig.frame_in_frame} nonsigVal={nonsig.frame_in_frame} />
          <StatRow label="Frameshift" sigVal={sig.frame_frameshift} nonsigVal={nonsig.frame_frameshift} />
          <StatRow label="Non-coding" sigVal={sig.frame_non_coding} nonsigVal={nonsig.frame_non_coding} />
          <StatRow label="Branch point found" sigVal={sig.bp_found_pct} nonsigVal={nonsig.bp_found_pct} format="pct" />
          <StatRow label="Mean ΔΨ" sigVal={sig.mean_delta_psi != null ? (sig.mean_delta_psi >= 0 ? `+${sig.mean_delta_psi.toFixed(3)}` : sig.mean_delta_psi.toFixed(3)) : null} nonsigVal={nonsig.mean_delta_psi != null ? (nonsig.mean_delta_psi >= 0 ? `+${nonsig.mean_delta_psi.toFixed(3)}` : nonsig.mean_delta_psi.toFixed(3)) : null} />
        </tbody>
      </table>

      {/* Consensus sequences */}
      <div className="grid grid-cols-2 gap-4 p-4 border-t border-border">
        <div>
          <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">
            Donor consensus (significant)
          </p>
          <code className="text-xs font-mono text-foreground">{sig.donor_consensus ?? "—"}</code>
        </div>
        <div>
          <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">
            Donor consensus (non-significant)
          </p>
          <code className="text-xs font-mono text-muted-foreground">{nonsig.donor_consensus ?? "—"}</code>
        </div>
        <div>
          <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">
            Acceptor consensus (significant)
          </p>
          <code className="text-xs font-mono text-foreground">{sig.acceptor_consensus ?? "—"}</code>
        </div>
        <div>
          <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1">
            Acceptor consensus (non-significant)
          </p>
          <code className="text-xs font-mono text-muted-foreground">{nonsig.acceptor_consensus ?? "—"}</code>
        </div>
      </div>
    </div>
  );
}
