"use client";

/**
 * PatternComparisonPanel
 * =======================
 * Side-by-side comparison of splice pattern statistics
 * between significant and non-significant event groups.
 */

import { useQuery } from "@tanstack/react-query";
import { getPatternComparison } from "@/lib/api/deep-analyses";
import type { GroupPatternStats, StatTestResult } from "@/lib/api/deep-analyses";
import { useT } from "@/contexts/LanguageContext";

interface Props {
  deepId: string;
}

function StatRow({
  label,
  sigVal,
  nonsigVal,
  format = "default",
  pValue,
  testName,
}: {
  label: string;
  sigVal: string | number | null;
  nonsigVal: string | number | null;
  format?: "default" | "pct" | "count";
  pValue?: number | null;
  testName?: string;
}) {
  const fmt = (v: string | number | null) => {
    if (v === null || v === undefined) return "—";
    if (format === "pct" && typeof v === "number") return `${v}%`;
    if (typeof v === "number") return v.toLocaleString();
    return v;
  };

  const pCell = pValue !== undefined ? (
    <td className={`px-3 py-2 text-[10px] tabular-nums text-center font-semibold ${
      pValue !== null && pValue < 0.01 ? "text-green-600 dark:text-green-400" :
      pValue !== null && pValue < 0.05 ? "text-amber-600 dark:text-amber-400" :
      "text-muted-foreground"
    }`} title={testName}>
      {pValue !== null ? pValue.toFixed(4) : "—"}
    </td>
  ) : (
    <td className="px-3 py-2" />
  );

  return (
    <tr className="border-b border-border/50">
      <td className="px-3 py-2 text-xs text-muted-foreground font-medium">{label}</td>
      <td className="px-3 py-2 text-xs text-foreground font-semibold tabular-nums text-center">
        {fmt(sigVal)}
      </td>
      <td className="px-3 py-2 text-xs text-muted-foreground tabular-nums text-center">
        {fmt(nonsigVal)}
      </td>
      {pCell}
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

  const { significant: sig, not_significant: nonsig, statistical_tests: tests } = data;

  // Build a lookup from feature key → StatTestResult
  const testMap = new Map<string, StatTestResult>();
  for (const t2 of tests ?? []) testMap.set(t2.feature, t2);

  const p = (key: string) => testMap.get(key);

  return (
    <div className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 border-b border-border">
          <tr>
            <th className="px-3 py-2.5 text-xs font-semibold text-left text-muted-foreground w-1/4">
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
            <th className="px-3 py-2.5 text-xs font-semibold text-center text-muted-foreground w-[90px]">
              p-value
            </th>
          </tr>
        </thead>
        <tbody>
          <StatRow label="SE events with features" sigVal={sig.n_se_with_features} nonsigVal={nonsig.n_se_with_features} />
          <StatRow label="Mean exon size" sigVal={sig.exon_size_mean != null ? `${sig.exon_size_mean} nt` : null} nonsigVal={nonsig.exon_size_mean != null ? `${nonsig.exon_size_mean} nt` : null} pValue={p("exon_size")?.p_value} testName={p("exon_size")?.test_name} />
          <StatRow label="Median exon size" sigVal={sig.exon_size_median != null ? `${sig.exon_size_median} nt` : null} nonsigVal={nonsig.exon_size_median != null ? `${nonsig.exon_size_median} nt` : null} />
          <StatRow label="Canonical GT (5'SS)" sigVal={sig.pct_canonical_gt} nonsigVal={nonsig.pct_canonical_gt} format="pct" pValue={p("canonical_gt")?.p_value} testName={p("canonical_gt")?.test_name} />
          <StatRow label="Canonical AG (3'SS)" sigVal={sig.pct_canonical_ag} nonsigVal={nonsig.pct_canonical_ag} format="pct" pValue={p("canonical_ag")?.p_value} testName={p("canonical_ag")?.test_name} />
          <StatRow label="Mean PPT score" sigVal={sig.ppt_mean_score != null ? `${Math.round(sig.ppt_mean_score * 100)}%` : null} nonsigVal={nonsig.ppt_mean_score != null ? `${Math.round(nonsig.ppt_mean_score * 100)}%` : null} pValue={p("ppt_score")?.p_value} testName={p("ppt_score")?.test_name} />
          <StatRow label="In-frame" sigVal={sig.frame_in_frame} nonsigVal={nonsig.frame_in_frame} pValue={p("in_frame_pct")?.p_value} testName={p("in_frame_pct")?.test_name} />
          <StatRow label="Frameshift" sigVal={sig.frame_frameshift} nonsigVal={nonsig.frame_frameshift} />
          <StatRow label="Non-coding" sigVal={sig.frame_non_coding} nonsigVal={nonsig.frame_non_coding} />
          <StatRow label="Branch point found" sigVal={sig.bp_found_pct} nonsigVal={nonsig.bp_found_pct} format="pct" pValue={p("bp_found")?.p_value} testName={p("bp_found")?.test_name} />
          <StatRow label="Mean ΔΨ" sigVal={sig.mean_delta_psi != null ? (sig.mean_delta_psi >= 0 ? `+${sig.mean_delta_psi.toFixed(3)}` : sig.mean_delta_psi.toFixed(3)) : null} nonsigVal={nonsig.mean_delta_psi != null ? (nonsig.mean_delta_psi >= 0 ? `+${nonsig.mean_delta_psi.toFixed(3)}` : nonsig.mean_delta_psi.toFixed(3)) : null} pValue={p("mean_delta_psi")?.p_value} testName={p("mean_delta_psi")?.test_name} />
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

      {/* P-value legend */}
      {tests && tests.length > 0 && (
        <div className="px-4 pb-3 flex items-center gap-4 text-[10px] text-muted-foreground">
          <span>p-value:</span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-2 h-2 rounded-full bg-green-500" />
            &lt; 0.01
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-2 h-2 rounded-full bg-amber-500" />
            &lt; 0.05
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-2 h-2 rounded-full bg-slate-400" />
            n.s.
          </span>
          <span className="ml-auto italic">Hover p-value for test name</span>
        </div>
      )}
    </div>
  );
}
