"use client";

/**
 * ComputeProgressBar
 * ===================
 * Polls the splice feature computation progress endpoint and displays
 * an animated progress bar during batch computation.
 */

import { useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getComputeProgress } from "@/lib/api/splice";
import { useT } from "@/contexts/LanguageContext";

interface Props {
  analysisId: string;
  /** Called when computation reaches 100%. */
  onComplete?: () => void;
}

export function ComputeProgressBar({ analysisId, onComplete }: Props) {
  const t = useT();
  const qc = useQueryClient();

  const { data } = useQuery({
    queryKey: ["compute-progress", analysisId],
    queryFn: () => getComputeProgress(analysisId),
    enabled: !!analysisId,
    refetchInterval: (query) => {
      const d = query.state.data;
      if (d?.done) return false; // stop polling
      return 2000; // poll every 2s
    },
    staleTime: 0,
  });

  // When a run we observed as "running" finishes, refresh every panel that
  // depends on the features (cards, patterns, comparison) and notify the host.
  const sawRunning = useRef(false);
  useEffect(() => {
    if (!data) return;
    if (data.status === "running") sawRunning.current = true;
    if (data.done && sawRunning.current) {
      sawRunning.current = false;
      qc.invalidateQueries({ queryKey: ["splice-feature"] });
      qc.invalidateQueries({ queryKey: ["splice-patterns"] });
      qc.invalidateQueries({ queryKey: ["pattern-comparison"] });
      qc.invalidateQueries({ queryKey: ["mane-transcript"] });
      onComplete?.();
    }
  }, [data, qc, onComplete]);

  if (!data) return null;

  if (data.status === "error") {
    return (
      <div className="rounded-lg border border-red-300 bg-red-50 p-3 text-xs text-red-700 space-y-1">
        <span className="font-semibold">{t("spliceView.computeError")}</span>
        {data.error && <p className="font-mono text-[10px] break-all">{data.error}</p>}
        <p className="text-[10px]">{t("spliceView.computeErrorHint")}</p>
      </div>
    );
  }

  if (data.done) return null;

  return (
    <div className="rounded-lg border border-border bg-card p-3 space-y-2 shadow-sm animate-in fade-in duration-300">
      <div className="flex items-center justify-between text-xs">
        <span className="font-semibold text-foreground flex items-center gap-1.5">
          <div className="w-3 h-3 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          {t("spliceView.computing")}
        </span>
        <span className="text-muted-foreground tabular-nums">
          {data.n_computed} / {data.n_se_events} SE events
        </span>
      </div>
      <div className="h-2 rounded-full bg-muted overflow-hidden">
        <div
          className="h-full rounded-full bg-blue-500 transition-all duration-500 ease-out"
          style={{ width: `${data.pct}%` }}
        />
      </div>
      <p className="text-[10px] text-muted-foreground">
        {data.pct}% — {t("spliceView.computingDesc")}
      </p>
    </div>
  );
}
