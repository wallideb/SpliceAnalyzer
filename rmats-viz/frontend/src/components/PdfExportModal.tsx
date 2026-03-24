"use client";

/**
 * PdfExportModal
 * ==============
 * Modal dialog for parameterized PDF export.
 *
 * The user selects which report sections to include:
 *   • Section A: Global Analysis Summary (always shown)
 *   • Section B: Significant Events Summary (deep only)
 *   • Section C: Significant vs Non-Significant Comparison (deep only)
 *   • Section D: Permutation Test (deep only)
 *   • Section E: hnRNP Motif Enrichment (deep only)
 *   • Section F: Enrichr Pathway Enrichment (deep only)
 *   • Top Splicing Events Table (always shown)
 */

import { useState } from "react";
import { useT } from "@/contexts/LanguageContext";

export type PdfSection = "a" | "b" | "c" | "d" | "e" | "f" | "top_events";

interface PdfExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onDownload: (sections: PdfSection[]) => void;
  isDownloading?: boolean;
  isDeepAnalysis?: boolean;
}

const ALL_SECTIONS: Array<{
  id: PdfSection;
  labelKey: string;
  descKey: string;
  deepOnly: boolean;
}> = [
  { id: "a", labelKey: "analysisDetail.pdfModal.sections.a", descKey: "analysisDetail.pdfModal.sections.aDesc", deepOnly: false },
  { id: "b", labelKey: "analysisDetail.pdfModal.sections.b", descKey: "analysisDetail.pdfModal.sections.bDesc", deepOnly: true },
  { id: "c", labelKey: "analysisDetail.pdfModal.sections.c", descKey: "analysisDetail.pdfModal.sections.cDesc", deepOnly: true },
  { id: "d", labelKey: "analysisDetail.pdfModal.sections.d", descKey: "analysisDetail.pdfModal.sections.dDesc", deepOnly: true },
  { id: "e", labelKey: "analysisDetail.pdfModal.sections.e", descKey: "analysisDetail.pdfModal.sections.eDesc", deepOnly: true },
  { id: "f", labelKey: "analysisDetail.pdfModal.sections.f", descKey: "analysisDetail.pdfModal.sections.fDesc", deepOnly: true },
  { id: "top_events", labelKey: "analysisDetail.pdfModal.sections.topEvents", descKey: "analysisDetail.pdfModal.sections.topEventsDesc", deepOnly: false },
];

export function PdfExportModal({
  isOpen,
  onClose,
  onDownload,
  isDownloading = false,
  isDeepAnalysis = false,
}: PdfExportModalProps) {
  const t = useT();
  const visibleSections = ALL_SECTIONS.filter((s) => !s.deepOnly || isDeepAnalysis);
  const [selected, setSelected] = useState<Set<PdfSection>>(
    () => new Set(visibleSections.map((s) => s.id)),
  );

  if (!isOpen) return null;

  const toggle = (id: PdfSection) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    const allVisible = visibleSections.map((s) => s.id);
    const allSelected = allVisible.every((id) => selected.has(id));
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(allVisible));
    }
  };

  const handleDownload = () => {
    onDownload(Array.from(selected));
  };

  const allChecked = visibleSections.every((s) => selected.has(s.id));

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
        aria-labelledby="pdf-modal-title"
        className="fixed inset-0 z-50 flex items-center justify-center p-4"
      >
        <div className="w-full max-w-lg bg-card border border-border rounded-2xl shadow-2xl p-6 space-y-5">

          {/* Header */}
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 id="pdf-modal-title" className="text-base font-bold text-foreground">
                {t("analysisDetail.pdfModal.title")}
              </h2>
              <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                {t("analysisDetail.pdfModal.description")}
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="shrink-0 p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              aria-label={t("analysisDetail.pdfModal.cancel")}
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Select all */}
          <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer hover:text-foreground transition-colors">
            <input
              type="checkbox"
              checked={allChecked}
              onChange={toggleAll}
              className="w-3.5 h-3.5 accent-blue-600"
            />
            {t("analysisDetail.pdfModal.selectAll")}
          </label>

          {/* Section checkboxes */}
          <div className="space-y-2 max-h-[50vh] overflow-y-auto">
            {visibleSections.map((sec) => (
              <label
                key={sec.id}
                className="flex items-start gap-3 px-3 py-2.5 rounded-lg border border-border hover:bg-muted/30 cursor-pointer transition-colors"
              >
                <input
                  type="checkbox"
                  checked={selected.has(sec.id)}
                  onChange={() => toggle(sec.id)}
                  className="mt-0.5 w-4 h-4 accent-blue-600"
                />
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-foreground">
                    {t(sec.labelKey)}
                  </p>
                  <p className="text-[11px] text-muted-foreground leading-relaxed mt-0.5">
                    {t(sec.descKey)}
                  </p>
                </div>
              </label>
            ))}
          </div>

          {/* Actions */}
          <div className="flex items-center justify-end gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium rounded-lg border border-border text-foreground hover:bg-muted transition-colors"
            >
              {t("analysisDetail.pdfModal.cancel")}
            </button>
            <button
              type="button"
              onClick={handleDownload}
              disabled={isDownloading || selected.size === 0}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-semibold bg-rose-600 hover:bg-rose-700 text-white rounded-lg disabled:opacity-50 transition-colors"
            >
              {isDownloading ? (
                <>
                  <svg className="animate-spin w-3.5 h-3.5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  PDF...
                </>
              ) : (
                <>
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  {t("analysisDetail.pdfModal.download")}
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
