"use client";

/**
 * SidebarNav
 * ===========
 * Left navigation panel for the Top-10 annotated cards view.
 * Each tab switches the "view mode" of every card without hiding the
 * event type badge or the top-rank number.
 *
 * The "StringDB" tab is only rendered when at least one mutated gene
 * has been defined for the analysis.
 */

import type { ViewMode } from "./types";

interface SidebarNavProps {
  activeMode: ViewMode;
  onChange: (mode: ViewMode) => void;
  /** Whether the sidebar is collapsed (mobile / narrow screens). */
  collapsed: boolean;
  onToggleCollapse: () => void;
  /** Whether to show the StringDB tab (requires at least one mutated gene). */
  showStringDB: boolean;
}

const BASE_TABS: { mode: ViewMode; label: string; icon: React.ReactNode }[] = [
  {
    mode: "gene",
    label: "Gène",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
      </svg>
    ),
  },
  {
    mode: "go",
    label: "GO / Ontologie",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
  },
  {
    mode: "panelapp",
    label: "PanelApp",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
      </svg>
    ),
  },
  {
    mode: "scores",
    label: "Scores rMATS",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
];

const STRINGDB_TAB: { mode: ViewMode; label: string; icon: React.ReactNode } = {
  mode: "stringdb",
  label: "Interactions",
  icon: (
    <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
    </svg>
  ),
};

export function SidebarNav({
  activeMode,
  onChange,
  collapsed,
  onToggleCollapse,
  showStringDB,
}: SidebarNavProps) {
  const tabs = showStringDB ? [...BASE_TABS, STRINGDB_TAB] : BASE_TABS;

  // If current mode is stringdb but it's no longer available, reset to gene
  const effectiveMode: ViewMode =
    activeMode === "stringdb" && !showStringDB ? "gene" : activeMode;

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
        {tabs.map(({ mode, label, icon }) => {
          const active = effectiveMode === mode;
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
              {!collapsed && <span className="truncate">{label}</span>}
              {collapsed && <span className="sr-only">{label}</span>}
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
