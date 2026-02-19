"use client";
import { useState } from "react";
import { useBasket } from "@/contexts/BasketContext";
import { EventTypeBadge } from "@/components/events/EventTypeBadge";
import type { EventType } from "@/types/event";
import { formatFDR } from "@/lib/utils";

export function BasketPanel() {
  const { items, removeItem, clearBasket, count } = useBasket();
  const [open, setOpen] = useState(false);

  return (
    <>
      {/* Floating trigger button */}
      <button
        onClick={() => setOpen(true)}
        title="Ouvrir le panier"
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
            d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13l-1.4 7h12.8M7 13H5.4M9 21a1 1 0 100-2 1 1 0 000 2zm10 0a1 1 0 100-2 1 1 0 000 2z"
          />
        </svg>
        <span className="text-sm font-semibold">Panier</span>
        {count > 0 && (
          <span className="bg-white text-blue-700 text-xs font-bold rounded-full px-2 py-0.5 min-w-[1.25rem] text-center">
            {count}
          </span>
        )}
      </button>

      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 bg-black/30 z-40"
          onClick={() => setOpen(false)}
        />
      )}

      {/* Drawer */}
      <aside
        className={`fixed top-0 right-0 h-full w-full sm:w-[480px] bg-white shadow-2xl z-50 flex flex-col transform transition-transform duration-300 ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {/* Drawer header */}
        <div className="flex items-center justify-between px-5 py-4 border-b bg-gray-50">
          <h2 className="text-base font-semibold text-gray-800">
            Panier — {count} événement{count !== 1 ? "s" : ""}
          </h2>
          <button
            onClick={() => setOpen(false)}
            className="text-gray-400 hover:text-gray-600 p-1 rounded"
            aria-label="Fermer"
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

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
          {count === 0 ? (
            <p className="text-sm text-gray-400 text-center mt-12">
              Le panier est vide.<br />
              Sélectionnez des événements puis cliquez sur&nbsp;
              <strong>Ajouter au panier</strong>.
            </p>
          ) : (
            items.map((item) => (
              <div
                key={item.event.id}
                className="border rounded-lg px-3 py-2.5 bg-white hover:bg-gray-50 flex items-start justify-between gap-2"
              >
                <div className="flex flex-col gap-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <EventTypeBadge type={item.event.event_type as EventType} />
                    <span className="font-semibold text-sm text-gray-800 truncate">
                      {item.event.gene_symbol ?? "—"}
                    </span>
                    <span className="text-xs text-gray-400">
                      {item.event.chr}:{item.event.strand}
                    </span>
                  </div>
                  <div className="text-xs text-gray-500 space-x-3">
                    <span>
                      Start: {item.event.exon_start?.toLocaleString("fr-FR") ?? "—"}
                    </span>
                    <span>
                      End: {item.event.exon_end?.toLocaleString("fr-FR") ?? "—"}
                    </span>
                  </div>
                  <div className="text-xs text-gray-500 space-x-3">
                    <span>
                      FDR:{" "}
                      <span className="font-medium text-gray-700">
                        {formatFDR(item.event.fdr)}
                      </span>
                    </span>
                    <span>
                      ΔPSI:{" "}
                      <span
                        className={`font-medium ${
                          (item.event.inc_level_difference ?? 0) > 0
                            ? "text-red-600"
                            : "text-blue-600"
                        }`}
                      >
                        {item.event.inc_level_difference?.toFixed(3) ?? "—"}
                      </span>
                    </span>
                  </div>
                  <div className="text-xs text-gray-400 truncate">
                    {item.analysisName}
                  </div>
                </div>
                <button
                  onClick={() => removeItem(item.event.id)}
                  title="Retirer du panier"
                  className="shrink-0 text-gray-300 hover:text-red-500 transition-colors p-0.5"
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
            ))
          )}
        </div>

        {/* Footer actions */}
        {count > 0 && (
          <div className="border-t px-4 py-3 flex items-center justify-between gap-3 bg-gray-50">
            <button
              onClick={clearBasket}
              className="text-sm text-red-500 hover:text-red-700 underline"
            >
              Vider le panier
            </button>
            <button
              disabled
              title="Fonctionnalité à venir"
              className="bg-blue-600 text-white text-sm px-4 py-2 rounded-md opacity-50 cursor-not-allowed"
            >
              Poursuivre l&apos;analyse →
            </button>
          </div>
        )}
      </aside>
    </>
  );
}
