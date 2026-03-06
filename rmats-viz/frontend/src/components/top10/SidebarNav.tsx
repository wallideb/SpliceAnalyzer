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
  /**
   * Optional extended modules for deep-analysis view.
   * Each key in this set adds a "coming soon" tab to the sidebar.
   * Supported: "pathways" | "motifs" | "splice"
   */
  activeModules?: Set<string>;
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

/** Extra tabs only shown in the deep-analysis view (coming soon). */
const EXTRA_TABS: Record<string, { mode: ViewMode; label: string; icon: React.ReactNode }> = {
  pathways: {
    mode: "pathways",
    label: "Voies moléc.",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
      </svg>
    ),
  },
  motifs: {
    mode: "motifs",
    label: "Motifs récur.",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
      </svg>
    ),
  },
  splice: {
    mode: "splice",
    label: "Sites consensus",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
      </svg>
    ),
  },
};

export function SidebarNav({
  activeMode,
  onChange,
  collapsed,
  onToggleCollapse,
  showStringDB,
  activeModules,
}: SidebarNavProps) {
  // Build tab list: base + optional stringdb + optional deep-analysis tabs
  const tabs = [
    ...BASE_TABS,
    ...(showStringDB ? [STRINGDB_TAB] : []),
    ...["pathways", "motifs", "splice"]
      .filter((k) => activeModules?.has(k))
      .map((k) => EXTRA_TABS[k]),
  ];

  // If current mode is no longer available, reset to gene
  const availableModes = new Set(tabs.map((t) => t.mode));
  const effectiveMode: ViewMode = availableModes.has(activeMode) ? activeMode : "gene";

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
