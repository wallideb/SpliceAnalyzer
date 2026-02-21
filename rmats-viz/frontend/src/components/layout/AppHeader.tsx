"use client";
import Link from "next/link";
import { useTheme } from "@/contexts/ThemeContext";

export function AppHeader() {
  const { theme, toggleTheme } = useTheme();

  return (
    <header className="border-b bg-card text-card-foreground shadow-sm sticky top-0 z-30 transition-colors duration-200">
      <div className="max-w-7xl mx-auto px-4 py-0 flex items-center justify-between h-14">

        {/* ── Logo + Titre ── */}
        <Link href="/analyses" className="flex items-center gap-2.5 group">
          {/* Logo SVG (public/logo.svg) */}
          <img
            src="/logo.svg"
            alt="SpliceAnalyzer logo"
            className="w-8 h-8 shrink-0"
            draggable={false}
          />
          <div className="leading-tight">
            <span className="block text-xl font-extrabold tracking-tight bg-gradient-to-r from-indigo-500 via-blue-500 to-cyan-500 dark:from-indigo-400 dark:via-blue-400 dark:to-cyan-300 bg-clip-text text-transparent">
              SpliceAnalyzer
            </span>
            <span className="block text-[10px] text-muted-foreground font-medium tracking-widest uppercase leading-none">
              rMATS · Splicing Events
            </span>
          </div>
        </Link>

        {/* ── Contrôles droite ── */}
        <div className="flex items-center gap-1.5">

          {/* Toggle dark/light mode */}
          <button
            onClick={toggleTheme}
            title={theme === "dark" ? "Passer en mode clair" : "Passer en mode sombre"}
            className="w-9 h-9 flex items-center justify-center rounded-lg hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
            aria-label="Basculer le thème"
          >
            {theme === "dark" ? (
              /* Soleil */
              <svg xmlns="http://www.w3.org/2000/svg" className="w-4.5 h-4.5 w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                <circle cx="12" cy="12" r="4"/>
                <path strokeLinecap="round" d="M12 2v2M12 20v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M2 12h2M20 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
              </svg>
            ) : (
              /* Lune */
              <svg xmlns="http://www.w3.org/2000/svg" className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>
              </svg>
            )}
          </button>

          {/* Compte utilisateur — placeholder auth future */}
          <button
            title="Compte utilisateur (authentification à venir)"
            className="w-9 h-9 flex items-center justify-center rounded-lg text-muted-foreground/40 cursor-not-allowed"
            disabled
            aria-label="Compte utilisateur"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/>
            </svg>
          </button>
        </div>
      </div>
    </header>
  );
}
