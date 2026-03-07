"use client";

/**
 * LanguageContext
 * ================
 * Provides `lang` (current language), `setLang` (switcher), and `t` (translation function).
 *
 * Usage:
 *   const t = useT();
 *   t("analyses.title")            → "My Analyses" or "Mes analyses"
 *   t("analyses.confirmDelete", { name: "PCBP1" }) → "Delete analysis «PCBP1»?"
 */

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { en } from "@/lib/i18n/en";
import { fr } from "@/lib/i18n/fr";

export type Language = "en" | "fr";

const DICTIONARIES: Record<Language, typeof en> = { en, fr };

interface LanguageContextValue {
  lang: Language;
  setLang: (lang: Language) => void;
  /** Translate a dot-separated key with optional {{var}} interpolation. */
  t: (key: string, vars?: Record<string, string | number>) => string;
}

const LanguageContext = createContext<LanguageContextValue>({
  lang: "en",
  setLang: () => {},
  t: (key) => key,
});

/** Walk a dot-path through a nested object, returning the leaf string or the key itself. */
function resolve(obj: Record<string, unknown>, key: string): string {
  const parts = key.split(".");
  let cur: unknown = obj;
  for (const part of parts) {
    if (cur !== null && typeof cur === "object" && part in (cur as Record<string, unknown>)) {
      cur = (cur as Record<string, unknown>)[part];
    } else {
      return key; // key not found — return raw key as fallback
    }
  }
  return typeof cur === "string" ? cur : key;
}

/** Replace {{varName}} placeholders with values from the vars map. */
function interpolate(str: string, vars?: Record<string, string | number>): string {
  if (!vars) return str;
  return str.replace(/\{\{(\w+)\}\}/g, (_, k) => String(vars[k] ?? `{{${k}}}`));
}

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Language>("en");

  // Restore persisted language on mount; also update the html lang attribute.
  useEffect(() => {
    const stored = localStorage.getItem("spliceanalyzer_lang") as Language | null;
    if (stored === "en" || stored === "fr") {
      setLangState(stored);
      document.documentElement.setAttribute("lang", stored);
    } else {
      // Default to English; set attribute explicitly in case layout.tsx left "fr".
      document.documentElement.setAttribute("lang", "en");
    }
  }, []);

  const setLang = useCallback((l: Language) => {
    setLangState(l);
    localStorage.setItem("spliceanalyzer_lang", l);
    document.documentElement.setAttribute("lang", l);
  }, []);

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>) => {
      const dict = DICTIONARIES[lang] as unknown as Record<string, unknown>;
      return interpolate(resolve(dict, key), vars);
    },
    [lang],
  );

  return (
    <LanguageContext.Provider value={{ lang, setLang, t }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  return useContext(LanguageContext);
}

/** Convenience hook — returns only the translation function. */
export function useT() {
  return useContext(LanguageContext).t;
}
