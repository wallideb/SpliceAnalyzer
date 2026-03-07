"use client";

/**
 * BasketPanel
 * ============
 * Floating basket button + slide-in drawer.
 */

import { useState } from "react";
import { useBasket } from "@/contexts/BasketContext";
import { useT } from "@/contexts/LanguageContext";
import { AnalysisOptionsModal } from "./AnalysisOptionsModal";
import { EventTypeBadge } from "@/components/events/EventTypeBadge";
import type { EventType } from "@/types/event";
import { formatFDR } from "@/lib/utils";

interface ModalTarget {
  analysisId: string;
  analysisName: string;
  eventCount: number;
}

export function BasketPanel() {
  const { items, removeItem, clearBasket, count } = useBasket();
  const t = useT();
  const [open, setOpen] = useState(false);
  const [modalTarget, setModalTarget] = useState<ModalTarget | null>(null);

  // Group basket items by analysisId
  const groups = items.reduce<
    Record<string, { analysisId: string; analysisName: string; events: typeof items }>
  >((acc, item) => {
    if (!acc[item.analysisId]) {
      acc[item.analysisId] = {
        analysisId: item.analysisId,
        analysisName: item.analysisName,
        events: [],
      };
    }
    acc[item.analysisId].events.push(item);
    return acc;
  }, {});

  const groupList = Object.values(groups);

  return (
    <>
      {/* ── Floating trigger button ── */}
      <button
        onClick={() => setOpen(true)}
        title={t("basket.openBasket")}
        className="fixed bottom-6 right-6 z-40 flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-3 rounded-full shadow-lg transition-colors"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-5 w-5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13l-1.4 7h12.8M9 21a1 1 0 100-2 1 1 0 000 2zm10 0a1 1 0 100-2 1 1 0 000 2z"
          />
        </svg>
        <span className="text-sm font-semibold">{t("basket.title")}</span>
        {count > 0 && (
          <span className="bg-white text-blue-700 text-xs font-bold rounded-full px-2 py-0.5 min-w-[1.25rem] text-center">
            {count}
          </span>
        )}
      </button>

      {/* ── Backdrop ── */}
      {open && (
        <div
          className="fixed inset-0 bg-black/30 z-40"
          onClick={() => setOpen(false)}
        />
      )}

      {/* ── Drawer ── */}
      <aside
        className={`fixed top-0 right-0 h-full w-full sm:w-[500px] bg-card border-l border-border shadow-2xl z-50 flex flex-col transform transition-transform duration-300 ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {/* Drawer header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border bg-muted/40">
          <div>
            <h2 className="text-base font-semibold text-foreground">
              {count !== 1 ? t("basket.headerPlural", { n: count }) : t("basket.header", { n: count })}
            </h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              {t("basket.subtitle")}
            </p>
          </div>
          <button
            onClick={() => setOpen(false)}
            className="text-muted-foreground hover:text-foreground p-1.5 rounded transition-colors"
            aria-label={t("basket.close")}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-5 w-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Top-10 always-included notice */}
        <div className="mx-4 mt-3 flex items-start gap-2 text-xs text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 rounded-lg px-3 py-2 leading-relaxed">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="w-4 h-4 shrink-0 mt-0.5 text-blue-500"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span dangerouslySetInnerHTML={{ __html: t("basket.top10Notice") }} />
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-5">
          {count === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 text-center mt-12 px-6">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="w-10 h-10 text-muted-foreground/30"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={1.5}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13l-1.4 7h12.8M9 21a1 1 0 100-2 1 1 0 000 2zm10 0a1 1 0 100-2 1 1 0 000 2z"
                />
              </svg>
              <p className="text-sm text-muted-foreground">
                {t("basket.empty.title")}
                <br />
                <span dangerouslySetInnerHTML={{ __html: t("basket.empty.subtitle") }} />
              </p>
            </div>
          ) : (
            groupList.map((group) => (
              <div key={group.analysisId} className="space-y-2">
                {/* Group header */}
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <p className="text-xs font-semibold text-foreground truncate max-w-[260px]">
                    {group.analysisName}
                  </p>
                  <span className="text-[11px] text-muted-foreground">
                    {group.events.length}{" "}
                    {group.events.length > 1 ? t("basket.eventPlural") : t("basket.event")}
                  </span>
                </div>

                {/* Event cards */}
                <div className="space-y-1.5">
                  {group.events.map((item) => (
                    <div
                      key={item.event.id}
                      className="border border-border rounded-lg px-3 py-2.5 bg-card hover:bg-muted/30 flex items-start justify-between gap-2 transition-colors"
                    >
                      <div className="flex flex-col gap-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <EventTypeBadge type={item.event.event_type as EventType} />
                          <span className="font-semibold text-sm text-foreground truncate">
                            {item.event.gene_symbol ?? "—"}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {item.event.chr}
                            {item.event.strand ? `:${item.event.strand}` : ""}
                          </span>
                        </div>
                        <div className="text-xs text-muted-foreground space-x-3">
                          <span>
                            FDR:{" "}
                            <span className="font-medium text-foreground">
                              {formatFDR(item.event.fdr)}
                            </span>
                          </span>
                          <span>
                            ΔPSI:{" "}
                            <span
                              className={`font-medium ${
                                (item.event.inc_level_difference ?? 0) > 0
                                  ? "text-red-600 dark:text-red-400"
                                  : "text-blue-600 dark:text-blue-400"
                              }`}
                            >
                              {item.event.inc_level_difference?.toFixed(3) ?? "—"}
                            </span>
                          </span>
                        </div>
                      </div>
                      <button
                        onClick={() => removeItem(item.event.id)}
                        title={t("basket.remove")}
                        className="shrink-0 text-muted-foreground/50 hover:text-destructive transition-colors p-0.5 mt-0.5"
                      >
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          className="h-4 w-4"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                          strokeWidth={2}
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                  ))}
                </div>

                {/* Per-group continue button */}
                <button
                  onClick={() =>
                    setModalTarget({
                      analysisId: group.analysisId,
                      analysisName: group.analysisName,
                      eventCount: group.events.length,
                    })
                  }
                  className="w-full inline-flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold px-4 py-2.5 rounded-xl transition-colors shadow-sm"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className="w-4 h-4"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                  </svg>
                  {t("basket.continueAnalysis")}
                </button>
              </div>
            ))
          )}
        </div>

        {/* Footer: clear all */}
        {count > 0 && (
          <div className="border-t border-border px-4 py-3 flex justify-end bg-muted/20">
            <button
              onClick={clearBasket}
              className="text-sm text-destructive hover:text-destructive/80 underline transition-colors"
            >
              {t("basket.clearBasket")}
            </button>
          </div>
        )}
      </aside>

      {/* ── Analysis options modal ── */}
      {modalTarget && (
        <AnalysisOptionsModal
          analysisId={modalTarget.analysisId}
          analysisName={modalTarget.analysisName}
          basketEventCount={modalTarget.eventCount}
          onClose={() => setModalTarget(null)}
        />
      )}
    </>
  );
}
