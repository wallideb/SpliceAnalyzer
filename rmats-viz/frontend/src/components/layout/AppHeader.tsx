"use client";
import Link from "next/link";
import { useTheme } from "@/contexts/ThemeContext";
import { useLanguage } from "@/contexts/LanguageContext";
import type { Language } from "@/contexts/LanguageContext";

export function AppHeader() {
  const { theme, toggleTheme } = useTheme();
  const { lang, setLang, t } = useLanguage();

  return (
    <header className="border-b bg-card text-card-foreground shadow-sm sticky top-0 z-30 transition-colors duration-200">
      <div className="max-w-7xl mx-auto px-4 py-0 flex items-center justify-between h-16">

        {/* ── Logo + Title ── */}
        <Link href="/analyses" className="flex items-center gap-3 group">
          <img
            src="/logo.svg"
            alt="SpliceAnalyzer logo"
            className="w-11 h-11 shrink-0"
            draggable={false}
          />
          <div className="leading-tight">
            <span className="block text-2xl font-extrabold tracking-tight bg-gradient-to-r from-indigo-500 via-blue-500 to-cyan-500 dark:from-indigo-400 dark:via-blue-400 dark:to-cyan-300 bg-clip-text text-transparent">
              SpliceAnalyzer
            </span>
            <span className="block text-[10px] text-muted-foreground font-medium tracking-widest uppercase leading-none">
              rMATS · Splicing Events
            </span>
          </div>
        </Link>

        {/* ── Right controls ── */}
        <div className="flex items-center gap-1.5">

          {/* Language selector — EN | FR pill */}
          <div className="flex items-center rounded-lg border border-border overflow-hidden text-xs font-semibold">
            {(["en", "fr"] as Language[]).map((l) => (
              <button
                key={l}
                onClick={() => setLang(l)}
                className={`px-2.5 py-1.5 transition-colors ${
                  lang === l
                    ? "bg-blue-600 text-white"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted"
                }`}
                aria-pressed={lang === l}
                aria-label={l === "en" ? "Switch to English" : "Passer en français"}
              >
                {l.toUpperCase()}
              </button>
            ))}
          </div>

          {/* Dark / light mode toggle */}
          <button
            onClick={toggleTheme}
            title={theme === "dark" ? t("header.themeLight") : t("header.themeDark")}
            className="w-9 h-9 flex items-center justify-center rounded-lg hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
            aria-label={t("header.toggleTheme")}
          >
            {theme === "dark" ? (
              /* Sun */
              <svg xmlns="http://www.w3.org/2000/svg" className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                <circle cx="12" cy="12" r="4"/>
                <path strokeLinecap="round" d="M12 2v2M12 20v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M2 12h2M20 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
              </svg>
            ) : (
              /* Moon */
              <svg xmlns="http://www.w3.org/2000/svg" className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>
              </svg>
            )}
          </button>

          {/* User account placeholder */}
          <button
            title={t("header.userAccount")}
            className="w-9 h-9 flex items-center justify-center rounded-lg text-muted-foreground/40 cursor-not-allowed"
            disabled
            aria-label={t("header.userAccount")}
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
