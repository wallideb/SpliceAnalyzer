"use client";

/**
 * ExcelExportModal
 * ================
 * Modal dialog for parameterized Excel export.
 *
 * The user selects which column groups to include:
 *   • core      – always checked (disabled), cannot be deselected
 *   • panelapp  – PanelApp disease panel confidence
 *   • go        – GO terms (BP / MF / CC)
 *   • stringdb  – STRING-DB highest combined score vs mutated genes
 *
 * A note explains that splice analysis details (logos, PPT tracks,
 * permutation test) are available in the PDF report only.
 */

import { useState } from "react";
import { useT } from "@/contexts/LanguageContext";

export type ExcelColumnGroup = "core" | "panelapp" | "go" | "stringdb";

interface ExcelExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onDownload: (groups: ExcelColumnGroup[]) => void;
  isDownloading?: boolean;
}

const OPTIONAL_GROUPS: Array<{
  id: Exclude<ExcelColumnGroup, "core">;
  labelKey: string;
  descKey: string;
}> = [
  { id: "panelapp", labelKey: "analysisDetail.excelModal.groups.panelapp",  descKey: "analysisDetail.excelModal.groups.panelappDesc" },
  { id: "go",       labelKey: "analysisDetail.excelModal.groups.go",        descKey: "analysisDetail.excelModal.groups.goDesc" },
  { id: "stringdb", labelKey: "analysisDetail.excelModal.groups.stringdb",  descKey: "analysisDetail.excelModal.groups.stringdbDesc" },
];

export function ExcelExportModal({
  isOpen,
  onClose,
  onDownload,
  isDownloading = false,
}: ExcelExportModalProps) {
  const t = useT();
  const [selected, setSelected] = useState<Set<Exclude<ExcelColumnGroup, "core">>>(new Set());

  if (!isOpen) return null;

  const toggle = (id: Exclude<ExcelColumnGroup, "core">) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleDownload = () => {
    const groups: ExcelColumnGroup[] = ["core", ...Array.from(selected)];
    onDownload(groups);
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden
      />

      {/* Dialog */}
      <div
        role="dialog"
        aria-modal
        aria-labelledby="excel-modal-title"
        className="fixed inset-0 z-50 flex items-center justify-center p-4"
      >
        <div className="w-full max-w-lg bg-card border border-border rounded-2xl shadow-2xl p-6 space-y-5">

          {/* Header */}
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 id="excel-modal-title" className="text-base font-bold text-foreground">
                {t("analysisDetail.excelModal.title")}
              </h2>
              <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                {t("analysisDetail.excelModal.description")}
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="shrink-0 p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              aria-label={t("analysisDetail.excelModal.cancel")}
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Column groups */}
          <div className="space-y-2">
            {/* Core — always included, not togglable */}
            <div className="flex items-start gap-3 px-3 py-2.5 rounded-lg bg-muted/40 border border-border opacity-75">
              <input
                type="checkbox"
                checked
                disabled
                className="mt-0.5 w-4 h-4 accent-blue-600"
                readOnly
              />
              <div className="min-w-0">
                <p className="text-sm font-semibold text-foreground">
                  {t("analysisDetail.excelModal.groups.core")}
                </p>
                <p className="text-[11px] text-muted-foreground leading-relaxed mt-0.5">
                  {t("analysisDetail.excelModal.groups.coreDesc")}
                </p>
              </div>
            </div>

            {/* Optional groups */}
            {OPTIONAL_GROUPS.map((grp) => (
              <label
                key={grp.id}
                className="flex items-start gap-3 px-3 py-2.5 rounded-lg border border-border hover:bg-muted/30 cursor-pointer transition-colors"
              >
                <input
                  type="checkbox"
                  checked={selected.has(grp.id)}
                  onChange={() => toggle(grp.id)}
                  className="mt-0.5 w-4 h-4 accent-blue-600"
                />
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-foreground">
                    {t(grp.labelKey)}
                  </p>
                  <p className="text-[11px] text-muted-foreground leading-relaxed mt-0.5">
                    {t(grp.descKey)}
                  </p>
                </div>
              </label>
            ))}
          </div>

          {/* Splice analysis note */}
          <div className="flex items-start gap-2 text-[11px] text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-lg px-3 py-2.5 leading-relaxed">
            <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>{t("analysisDetail.excelModal.spliceNote")}</span>
          </div>

          {/* Actions */}
          <div className="flex items-center justify-end gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium rounded-lg border border-border text-foreground hover:bg-muted transition-colors"
            >
              {t("analysisDetail.excelModal.cancel")}
            </button>
            <button
              type="button"
              onClick={handleDownload}
              disabled={isDownloading}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-semibold bg-green-600 hover:bg-green-700 text-white rounded-lg disabled:opacity-50 transition-colors"
            >
              {isDownloading ? (
                <>
                  <svg className="animate-spin w-3.5 h-3.5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Excel…
                </>
              ) : (
                <>
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  {t("analysisDetail.excelModal.download")}
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
