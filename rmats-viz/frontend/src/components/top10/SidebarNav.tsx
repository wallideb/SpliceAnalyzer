"use client";

/**
 * SidebarNav
 * ===========
 * Left navigation panel for the Top-10 annotated cards view.
 * Each tab switches the "view mode" of every card without hiding the
 * event type badge or the top-rank number.
 */

import type { ViewMode } from "./types";

interface SidebarNavProps {
  activeMode: ViewMode;
  onChange: (mode: ViewMode) => void;
  /** Whether the sidebar is collapsed (mobile / narrow screens). */
  collapsed: boolean;
  onToggleCollapse: () => void;
}

const TABS: { mode: ViewMode; label: string; shortLabel: string; icon: React.ReactNode }[] = [
  {
    mode: "gene",
    label: "Gène",
    shortLabel: "Gène",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
      </svg>
    ),
  },
  {
    mode: "go",
    label: "GO / Ontologie",
    shortLabel: "GO",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
  },
  {
    mode: "panelapp",
    label: "PanelApp",
    shortLabel: "Panel",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
      </svg>
    ),
  },
  {
    mode: "scores",
    label: "Scores rMATS",
    shortLabel: "rMATS",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
  {
    mode: "conservation",
    label: "Conservation",
    shortLabel: "Cons.",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
];

export function SidebarNav({ activeMode, onChange, collapsed, onToggleCollapse }: SidebarNavProps) {
  return (
    <aside
      className={`shrink-0 flex flex-col border-r border-border bg-card transition-all duration-200 ${
        collapsed ? "w-12" : "w-44"
      }`}
    >
      {/* Toggle button */}
      <button
        onClick={onToggleCollapse}
        className="flex items-center justify-center h-10 border-b border-border text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
        title={collapsed ? "Afficher le volet" : "Masquer le volet"}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className={`w-4 h-4 transition-transform duration-200 ${collapsed ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
      </button>

      {/* Nav items */}
      <nav className="flex flex-col gap-1 p-1.5">
        {TABS.map(({ mode, label, shortLabel, icon }) => {
          const active = activeMode === mode;
          return (
            <button
              key={mode}
              onClick={() => onChange(mode)}
              title={collapsed ? label : undefined}
              className={`flex items-center gap-2.5 px-2 py-2 rounded-lg text-sm font-medium text-left transition-colors ${
                active
                  ? "bg-blue-600 text-white shadow-sm"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted"
              }`}
            >
              <span className="shrink-0">{icon}</span>
              {!collapsed && (
                <span className="truncate">{label}</span>
              )}
              {collapsed && (
                <span className="sr-only">{label}</span>
              )}
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
