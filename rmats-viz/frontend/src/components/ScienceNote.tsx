"use client";

/**
 * ScienceNote
 * ===========
 * A compact, collapsible scientific note attached to analysis panels.
 *
 * Props:
 *   title   – short heading (e.g. "Statistical method")
 *   body    – explanation text (may contain HTML; rendered via
 *             dangerouslySetInnerHTML)
 *   refs    – array of reference IDs from lib/references.ts to cite
 *             inline at the bottom of the note
 *
 * The note starts collapsed and expands on click.  A small ◈ icon
 * distinguishes it from regular UI elements.
 */

import { useState } from "react";
import { REFERENCES, pubmedUrl, doiUrl } from "@/lib/references";

interface ScienceNoteProps {
  title: string;
  body: string;
  refs?: string[];
  defaultOpen?: boolean;
}

export function ScienceNote({
  title,
  body,
  refs = [],
  defaultOpen = false,
}: ScienceNoteProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="mt-3 rounded-lg border border-blue-200 dark:border-blue-800/60 bg-blue-50/60 dark:bg-blue-950/20 text-[11px]">
      {/* Toggle header */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left text-blue-700 dark:text-blue-300 font-semibold hover:bg-blue-100/60 dark:hover:bg-blue-900/30 rounded-lg transition-colors"
        aria-expanded={open}
      >
        <span className="text-[10px] opacity-70 shrink-0">◈</span>
        <span className="flex-1">{title}</span>
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className={`w-3.5 h-3.5 shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2.5}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Body */}
      {open && (
        <div className="px-3 pb-3 space-y-2">
          <p
            className="text-blue-900/80 dark:text-blue-200/80 leading-relaxed"
            dangerouslySetInnerHTML={{ __html: body }}
          />

          {/* Reference list */}
          {refs.length > 0 && (
            <ul className="space-y-1 border-t border-blue-200 dark:border-blue-800/40 pt-2">
              {refs.map((refId) => {
                const ref = REFERENCES[refId];
                if (!ref) return null;
                const pmid = pubmedUrl(ref);
                const doi = doiUrl(ref);
                const href = pmid ?? doi ?? null;
                return (
                  <li key={refId} className="flex items-start gap-1 text-blue-800/70 dark:text-blue-300/70 leading-snug">
                    <span className="shrink-0 font-semibold">[{ref.short}]</span>
                    {href ? (
                      <a
                        href={href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="hover:underline"
                      >
                        {ref.full}
                      </a>
                    ) : (
                      <span>{ref.full}</span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
