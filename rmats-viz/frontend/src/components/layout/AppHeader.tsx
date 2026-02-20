"use client";
import Link from "next/link";
import { useTheme } from "@/contexts/ThemeContext";

export function AppHeader() {
  const { theme, toggleTheme } = useTheme();

  return (
    <header className="border-b bg-card text-card-foreground shadow-sm sticky top-0 z-30 transition-colors duration-200">
      <div className="max-w-7xl mx-auto px-4 py-0 flex items-center justify-between h-14">
        {/* Logo + Title */}
        <Link href="/analyses" className="flex items-center gap-2.5 group">
          {/* DNA helix icon */}
          <DnaIcon />
          <div className="leading-tight">
            <span className="text-xl font-extrabold tracking-tight bg-gradient-to-r from-blue-600 to-cyan-500 dark:from-blue-400 dark:to-cyan-300 bg-clip-text text-transparent">
              SpliceAnalyzer
            </span>
            <span className="block text-[10px] text-muted-foreground font-medium tracking-widest uppercase">
              rMATS · Splicing Events
            </span>
          </div>
        </Link>

        {/* Right side controls */}
        <div className="flex items-center gap-2">
          {/* Dark mode toggle */}
          <button
            onClick={toggleTheme}
            title={theme === "dark" ? "Passer en mode clair" : "Passer en mode sombre"}
            className="w-9 h-9 flex items-center justify-center rounded-lg hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
            aria-label="Basculer le thème"
          >
            {theme === "dark" ? (
              /* Sun icon */
              <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                <circle cx="12" cy="12" r="4" />
                <path strokeLinecap="round" d="M12 2v2M12 20v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M2 12h2M20 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
              </svg>
            ) : (
              /* Moon icon */
              <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
              </svg>
            )}
          </button>

          {/* User account placeholder — designed for future auth system */}
          <button
            title="Compte utilisateur (à venir)"
            className="w-9 h-9 flex items-center justify-center rounded-lg hover:bg-muted transition-colors text-muted-foreground hover:text-foreground opacity-60 cursor-not-allowed"
            disabled
            aria-label="Compte utilisateur"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
          </button>
        </div>
      </div>
    </header>
  );
}

function DnaIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className="w-8 h-8 shrink-0"
      viewBox="0 0 32 32"
      fill="none"
    >
      {/* Double helix strands */}
      <path
        d="M8 4 C8 4 14 8 16 12 C18 16 24 20 24 20"
        stroke="#3b82f6"
        strokeWidth="2.5"
        strokeLinecap="round"
        fill="none"
      />
      <path
        d="M24 4 C24 4 18 8 16 12 C14 16 8 20 8 20"
        stroke="#06b6d4"
        strokeWidth="2.5"
        strokeLinecap="round"
        fill="none"
      />
      <path
        d="M8 20 C8 20 14 24 16 26 C18 28 24 28 24 28"
        stroke="#3b82f6"
        strokeWidth="2.5"
        strokeLinecap="round"
        fill="none"
        opacity="0.6"
      />
      <path
        d="M24 20 C24 20 18 24 16 26 C14 28 8 28 8 28"
        stroke="#06b6d4"
        strokeWidth="2.5"
        strokeLinecap="round"
        fill="none"
        opacity="0.6"
      />
      {/* Base pairs */}
      <line x1="11.5" y1="9.5" x2="20.5" y2="9.5" stroke="#94a3b8" strokeWidth="1.5" strokeLinecap="round" />
      <line x1="11" y1="13" x2="21" y2="13" stroke="#94a3b8" strokeWidth="1.5" strokeLinecap="round" />
      <line x1="11.5" y1="16.5" x2="20.5" y2="16.5" stroke="#94a3b8" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}
