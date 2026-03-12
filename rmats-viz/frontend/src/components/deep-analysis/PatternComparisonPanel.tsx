"use client";

/**
 * PatternComparisonPanel
 * =======================
 * Side-by-side comparison of splice-site sequence logos
 * between significant and non-significant event groups.
 *
 * The feature comparison table and reading frame breakdown have been
 * moved to the MotifPatternPanel (motifs tab) for better organisation.
 */

import { useQuery } from "@tanstack/react-query";
import { getPatternComparison } from "@/lib/api/deep-analyses";
import type { StatTestResult } from "@/lib/api/deep-analyses";
import { useT } from "@/contexts/LanguageContext";
import { ConsensusLogoPanel } from "@/components/top10/ConsensusLogoPanel";

interface Props {
  deepId: string;
}

/** Annotation banner showing a statistical test result between two figure panels */
function TestAnnotation({ test }: { test: StatTestResult | undefined }) {
  if (!test || test.p_value == null) return null;
  const pStr = test.p_value < 0.0001
    ? test.p_value.toExponential(2)
    : test.p_value.toFixed(4);
  const color = test.p_value < 0.01
    ? "text-green-600 dark:text-green-400"
    : test.p_value < 0.05
      ? "text-amber-600 dark:text-amber-400"
      : "text-muted-foreground";
  const sigLabel = test.significant ? "significant" : "n.s.";
  return (
    <div className="flex items-center justify-center gap-2 py-1.5 px-3 rounded-lg bg-muted/40 border border-border text-[10px]">
      <span className="text-muted-foreground">{test.test_name}:</span>
      <span className={`font-mono font-semibold ${color}`}>
        p = {pStr}
      </span>
      <span className={`px-1.5 py-0.5 rounded text-[9px] font-medium ${
        test.significant
          ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
          : "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"
      }`}>
        {sigLabel}
      </span>
    </div>
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

  const testMap = new Map<string, StatTestResult>();
  for (const t2 of tests ?? []) testMap.set(t2.feature, t2);
  const p = (key: string) => testMap.get(key);

  return (
    <div className="space-y-6">
      {/* ── 5'SS Donor logos side-by-side ── */}
      {(sig.donor_pwm || nonsig.donor_pwm) && (
        <div className="rounded-xl border border-border bg-card shadow-sm p-4 space-y-3">
          <p className="text-[11px] font-bold text-foreground uppercase tracking-wide">
            5&apos;SS Donor sequence logo (9 nt)
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <p className="text-[10px] font-semibold text-green-700 dark:text-green-400 mb-2">
                {t("deepAnalysis.significant")} ({sig.n_se_with_features})
              </p>
              {sig.donor_pwm && sig.donor_pwm.length > 0 ? (
                <>
                  <ConsensusLogoPanel
                    pwm={sig.donor_pwm}
                    title=""
                    startPosition={-3}
                    skipZero
                    canonicalPositions={[1, 2]}
                    id="cmp-donor-sig"
                    nSequences={sig.n_se_with_features}
                  />
                  {sig.donor_consensus && (
                    <p className="text-[10px] text-muted-foreground mt-1">
                      IUPAC: <code className="font-mono font-bold text-foreground">{sig.donor_consensus}</code>
                    </p>
                  )}
                </>
              ) : (
                <p className="text-[10px] text-muted-foreground">No data</p>
              )}
            </div>
            <div>
              <p className="text-[10px] font-semibold text-slate-500 mb-2">
                {t("deepAnalysis.notSignificant")} ({nonsig.n_se_with_features})
              </p>
              {nonsig.donor_pwm && nonsig.donor_pwm.length > 0 ? (
                <>
                  <ConsensusLogoPanel
                    pwm={nonsig.donor_pwm}
                    title=""
                    startPosition={-3}
                    skipZero
                    canonicalPositions={[1, 2]}
                    id="cmp-donor-nonsig"
                    nSequences={nonsig.n_se_with_features}
                  />
                  {nonsig.donor_consensus && (
                    <p className="text-[10px] text-muted-foreground mt-1">
                      IUPAC: <code className="font-mono text-muted-foreground">{nonsig.donor_consensus}</code>
                    </p>
                  )}
                </>
              ) : (
                <p className="text-[10px] text-muted-foreground">No data</p>
              )}
            </div>
          </div>
          <TestAnnotation test={p("canonical_gt")} />
        </div>
      )}

      {/* ── 3'SS Acceptor logos side-by-side ── */}
      {(sig.acceptor_pwm || nonsig.acceptor_pwm) && (
        <div className="rounded-xl border border-border bg-card shadow-sm p-4 space-y-3">
          <p className="text-[11px] font-bold text-foreground uppercase tracking-wide">
            3&apos;SS Acceptor sequence logo (23 nt)
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <p className="text-[10px] font-semibold text-green-700 dark:text-green-400 mb-2">
                {t("deepAnalysis.significant")} ({sig.n_se_with_features})
              </p>
              {sig.acceptor_pwm && sig.acceptor_pwm.length > 0 ? (
                <>
                  <ConsensusLogoPanel
                    pwm={sig.acceptor_pwm}
                    title=""
                    startPosition={-20}
                    skipZero
                    canonicalPositions={[-2, -1]}
                    id="cmp-acceptor-sig"
                    nSequences={sig.n_se_with_features}
                  />
                  {sig.acceptor_consensus && (
                    <p className="text-[10px] text-muted-foreground mt-1">
                      IUPAC: <code className="font-mono font-bold text-foreground">{sig.acceptor_consensus}</code>
                    </p>
                  )}
                </>
              ) : (
                <p className="text-[10px] text-muted-foreground">No data</p>
              )}
            </div>
            <div>
              <p className="text-[10px] font-semibold text-slate-500 mb-2">
                {t("deepAnalysis.notSignificant")} ({nonsig.n_se_with_features})
              </p>
              {nonsig.acceptor_pwm && nonsig.acceptor_pwm.length > 0 ? (
                <>
                  <ConsensusLogoPanel
                    pwm={nonsig.acceptor_pwm}
                    title=""
                    startPosition={-20}
                    skipZero
                    canonicalPositions={[-2, -1]}
                    id="cmp-acceptor-nonsig"
                    nSequences={nonsig.n_se_with_features}
                  />
                  {nonsig.acceptor_consensus && (
                    <p className="text-[10px] text-muted-foreground mt-1">
                      IUPAC: <code className="font-mono text-muted-foreground">{nonsig.acceptor_consensus}</code>
                    </p>
                  )}
                </>
              ) : (
                <p className="text-[10px] text-muted-foreground">No data</p>
              )}
            </div>
          </div>
          <TestAnnotation test={p("canonical_ag")} />
        </div>
      )}

      {/* ── Upstream flanking exon 5'SS donor logos ── */}
      {(sig.upstream_donor_pwm || nonsig.upstream_donor_pwm) && (
        <div className="rounded-xl border border-border bg-card shadow-sm p-4 space-y-3">
          <p className="text-[11px] font-bold text-foreground uppercase tracking-wide">
            Upstream exon 5&apos;SS Donor (9 nt)
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <p className="text-[10px] font-semibold text-green-700 dark:text-green-400 mb-2">
                {t("deepAnalysis.significant")} ({sig.n_se_with_features})
              </p>
              {sig.upstream_donor_pwm && sig.upstream_donor_pwm.length > 0 ? (
                <>
                  <ConsensusLogoPanel pwm={sig.upstream_donor_pwm} title="" startPosition={-3} skipZero canonicalPositions={[1, 2]} id="cmp-up-donor-sig" nSequences={sig.n_se_with_features} />
                  {sig.upstream_donor_consensus && (
                    <p className="text-[10px] text-muted-foreground mt-1">
                      IUPAC: <code className="font-mono text-muted-foreground">{sig.upstream_donor_consensus}</code>
                    </p>
                  )}
                </>
              ) : (
                <p className="text-[10px] text-muted-foreground">No data</p>
              )}
            </div>
            <div>
              <p className="text-[10px] font-semibold text-slate-500 mb-2">
                {t("deepAnalysis.notSignificant")} ({nonsig.n_se_with_features})
              </p>
              {nonsig.upstream_donor_pwm && nonsig.upstream_donor_pwm.length > 0 ? (
                <>
                  <ConsensusLogoPanel pwm={nonsig.upstream_donor_pwm} title="" startPosition={-3} skipZero canonicalPositions={[1, 2]} id="cmp-up-donor-nonsig" nSequences={nonsig.n_se_with_features} />
                  {nonsig.upstream_donor_consensus && (
                    <p className="text-[10px] text-muted-foreground mt-1">
                      IUPAC: <code className="font-mono text-muted-foreground">{nonsig.upstream_donor_consensus}</code>
                    </p>
                  )}
                </>
              ) : (
                <p className="text-[10px] text-muted-foreground">No data</p>
              )}
            </div>
          </div>
          <TestAnnotation test={p("upstream_canonical_gt")} />
        </div>
      )}

      {/* ── Downstream flanking exon 3'SS acceptor logos ── */}
      {(sig.downstream_acceptor_pwm || nonsig.downstream_acceptor_pwm) && (
        <div className="rounded-xl border border-border bg-card shadow-sm p-4 space-y-3">
          <p className="text-[11px] font-bold text-foreground uppercase tracking-wide">
            Downstream exon 3&apos;SS Acceptor (23 nt)
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <p className="text-[10px] font-semibold text-green-700 dark:text-green-400 mb-2">
                {t("deepAnalysis.significant")} ({sig.n_se_with_features})
              </p>
              {sig.downstream_acceptor_pwm && sig.downstream_acceptor_pwm.length > 0 ? (
                <>
                  <ConsensusLogoPanel pwm={sig.downstream_acceptor_pwm} title="" startPosition={-20} skipZero canonicalPositions={[-2, -1]} id="cmp-dn-acc-sig" nSequences={sig.n_se_with_features} />
                  {sig.downstream_acceptor_consensus && (
                    <p className="text-[10px] text-muted-foreground mt-1">
                      IUPAC: <code className="font-mono text-muted-foreground">{sig.downstream_acceptor_consensus}</code>
                    </p>
                  )}
                </>
              ) : (
                <p className="text-[10px] text-muted-foreground">No data</p>
              )}
            </div>
            <div>
              <p className="text-[10px] font-semibold text-slate-500 mb-2">
                {t("deepAnalysis.notSignificant")} ({nonsig.n_se_with_features})
              </p>
              {nonsig.downstream_acceptor_pwm && nonsig.downstream_acceptor_pwm.length > 0 ? (
                <>
                  <ConsensusLogoPanel pwm={nonsig.downstream_acceptor_pwm} title="" startPosition={-20} skipZero canonicalPositions={[-2, -1]} id="cmp-dn-acc-nonsig" nSequences={nonsig.n_se_with_features} />
                  {nonsig.downstream_acceptor_consensus && (
                    <p className="text-[10px] text-muted-foreground mt-1">
                      IUPAC: <code className="font-mono text-muted-foreground">{nonsig.downstream_acceptor_consensus}</code>
                    </p>
                  )}
                </>
              ) : (
                <p className="text-[10px] text-muted-foreground">No data</p>
              )}
            </div>
          </div>
          <TestAnnotation test={p("downstream_canonical_ag")} />
        </div>
      )}

      {/* ── Methodology ── */}
      <div className="rounded-xl border border-border bg-muted/30 p-4 space-y-2">
        <p className="text-[11px] font-bold text-foreground uppercase tracking-wide">
          Methodology
        </p>
        <div className="text-[10px] text-muted-foreground leading-relaxed space-y-1.5">
          <p>
            Events are classified as <span className="font-semibold text-green-700 dark:text-green-400">significant</span> when
            both FDR and |ΔΨ| thresholds are met simultaneously.
            All remaining events form the <span className="font-semibold text-slate-500">non-significant</span> control group.
          </p>
          <p>
            <strong>Sequence logos</strong> follow the WebLogo / Schneider &amp; Stephens (1990) convention:
            column height reflects information content (bits), letter height is proportional to nucleotide frequency.
            Canonical dinucleotides (GT at +1/+2 for 5&apos;SS, AG at -2/-1 for 3&apos;SS) are highlighted in yellow.
          </p>
          <p>
            <strong>Statistical tests:</strong> continuous metrics (exon size, PPT score, mean ΔΨ) are compared
            using Welch&apos;s t-test (unequal variances). Proportions (canonical GT/AG, in-frame %, branch point found)
            use a two-proportion z-test. All tests are two-tailed.
          </p>
          <p>
            <strong>Reading frame:</strong> exon skipping is classified as in-frame (exon length divisible by 3)
            or frameshift based on the MANE Select transcript annotation when available, otherwise by exon size divisibility.
          </p>
        </div>
      </div>
    </div>
  );
}
