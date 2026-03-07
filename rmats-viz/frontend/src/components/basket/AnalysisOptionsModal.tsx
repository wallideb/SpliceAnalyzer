"use client";

/**
 * AnalysisOptionsModal
 * =====================
 * Contextual modal that appears when the user clicks "Continue Analysis"
 * in the basket panel.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useT } from "@/contexts/LanguageContext";

interface AnalysisOptionsModalProps {
  analysisId: string;
  analysisName: string;
  basketEventCount: number;
  onClose: () => void;
}

const ALWAYS_INCLUDED_KEYS = [
  "analysisOptions.alwaysIncludedModules.gene",
  "analysisOptions.alwaysIncludedModules.go",
  "analysisOptions.alwaysIncludedModules.panelapp",
  "analysisOptions.alwaysIncludedModules.scores",
] as const;

const OPTIONAL_MODULE_KEYS: { key: string; labelKey: string; descKey: string }[] = [
  {
    key: "stringdb",
    labelKey: "analysisOptions.modules.stringdb.label",
    descKey: "analysisOptions.modules.stringdb.description",
  },
  {
    key: "pathways",
    labelKey: "analysisOptions.modules.pathways.label",
    descKey: "analysisOptions.modules.pathways.description",
  },
  {
    key: "motifs",
    labelKey: "analysisOptions.modules.motifs.label",
    descKey: "analysisOptions.modules.motifs.description",
  },
  {
    key: "splice",
    labelKey: "analysisOptions.modules.splice.label",
    descKey: "analysisOptions.modules.splice.description",
  },
];

export function AnalysisOptionsModal({
  analysisId,
  analysisName,
  basketEventCount,
  onClose,
}: AnalysisOptionsModalProps) {
  const router = useRouter();
  const t = useT();
  const [selected, setSelected] = useState<Set<string>>(new Set(["stringdb"]));

  const toggle = (key: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const handleLaunch = () => {
    const modules = Array.from(selected).join(",");
    const qs = modules ? `?modules=${modules}` : "";
    router.push(`/analyses/${analysisId}/deep-analysis${qs}`);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div className="relative bg-card border border-border rounded-2xl shadow-2xl max-w-lg w-full p-6 space-y-5 z-10">
        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold text-foreground">
              {t("analysisOptions.title")}
            </h2>
            <p className="text-sm text-muted-foreground mt-0.5 truncate max-w-[340px]">
              {analysisName}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground p-1 rounded transition-colors shrink-0"
            aria-label={t("basket.close")}
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Always-included block */}
        <div className="bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 rounded-xl p-4 space-y-3">
          <p className="text-xs font-semibold text-blue-700 dark:text-blue-300 uppercase tracking-wide">
            {t("analysisOptions.alwaysIncluded")}
          </p>
          <div className="grid grid-cols-2 gap-1.5">
            {ALWAYS_INCLUDED_KEYS.map((key) => (
              <div key={key} className="flex items-center gap-1.5 text-xs text-blue-800 dark:text-blue-200">
                <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5 text-blue-500 dark:text-blue-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
                {t(key)}
              </div>
            ))}
          </div>
          <p className="text-[11px] text-blue-600 dark:text-blue-400 leading-relaxed">
            {basketEventCount > 0 && (
              <>
                <strong>{basketEventCount}</strong>{" "}
                {basketEventCount > 1
                  ? t("analysisOptions.basketEventsPrefixPlural", { n: basketEventCount })
                  : t("analysisOptions.basketEventsPrefix", { n: basketEventCount })}{" "}
              </>
            )}
            <strong>Top 10</strong> {t("analysisOptions.top10AlwaysIncluded")}
          </p>
        </div>

        {/* Optional modules */}
        <div className="space-y-2">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            {t("analysisOptions.optionalModules")}
          </p>
          <div className="space-y-2">
            {OPTIONAL_MODULE_KEYS.map((mod) => {
              const checked = selected.has(mod.key);
              return (
                <label
                  key={mod.key}
                  className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${
                    checked
                      ? "border-blue-500 bg-blue-50 dark:bg-blue-950/20 dark:border-blue-600"
                      : "border-border hover:bg-muted/50"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggle(mod.key)}
                    className="mt-0.5 w-4 h-4 rounded border-border accent-blue-600 cursor-pointer shrink-0"
                  />
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-foreground">{t(mod.labelKey)}</p>
                    <p className="text-[11px] text-muted-foreground leading-relaxed">{t(mod.descKey)}</p>
                  </div>
                </label>
              );
            })}
          </div>
        </div>

        {/* Footer actions */}
        <div className="flex gap-2 justify-end pt-1 border-t border-border">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg border border-border text-sm text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            {t("analysisOptions.cancel")}
          </button>
          <button
            onClick={handleLaunch}
            className="inline-flex items-center gap-1.5 px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-lg transition-colors shadow-sm"
          >
            {t("analysisOptions.launch")}
            <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
