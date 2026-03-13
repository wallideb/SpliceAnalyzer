"use client";

/**
 * SidebarNav
 * ===========
 * Left navigation panel for the Top-10 annotated cards view.
 */

import type { ViewMode } from "./types";
import { useT } from "@/contexts/LanguageContext";

interface SidebarNavProps {
  activeMode: ViewMode;
  onChange: (mode: ViewMode) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
  showStringDB: boolean;
  activeModules?: Set<string>;
}

type TabDef = { mode: ViewMode; labelKey: string; icon: React.ReactNode };

const BASE_TABS: TabDef[] = [
  {
    mode: "gene",
    labelKey: "sidebarNav.tabs.annotatedEvents",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
      </svg>
    ),
  },
];

const STRINGDB_TAB: TabDef = {
  mode: "stringdb",
  labelKey: "sidebarNav.tabs.interactions",
  icon: (
    <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
    </svg>
  ),
};

const EXTRA_TABS: Record<string, TabDef> = {
  pathways: {
    mode: "pathways",
    labelKey: "sidebarNav.tabs.pathways",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
      </svg>
    ),
  },
  motifs: {
    mode: "motifs",
    labelKey: "sidebarNav.tabs.motifs",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
      </svg>
    ),
  },
  splice: {
    mode: "splice",
    labelKey: "sidebarNav.tabs.splice",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
      </svg>
    ),
  },
  hnrnp: {
    mode: "hnrnp",
    labelKey: "sidebarNav.tabs.hnrnp",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
      </svg>
    ),
  },
  enrichr: {
    mode: "enrichr",
    labelKey: "sidebarNav.tabs.enrichr",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3v11.25A2.25 2.25 0 006 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0118 16.5h-2.25m-7.5 0h7.5m-7.5 0l-1 3m8.5-3l1 3m0 0l.5 1.5m-.5-1.5h-9.5m0 0l-.5 1.5" />
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
  const t = useT();

  const tabs = [
    ...BASE_TABS,
    ...(showStringDB ? [STRINGDB_TAB] : []),
    ...["pathways", "motifs", "splice", "hnrnp", "enrichr"]
      .filter((k) => activeModules?.has(k))
      .map((k) => EXTRA_TABS[k]),
  ];

  const availableModes = new Set(tabs.map((tb) => tb.mode));
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
        title={collapsed ? t("sidebarNav.expand") : t("sidebarNav.collapse")}
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
        {tabs.map(({ mode, labelKey, icon }) => {
          const label = t(labelKey);
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
