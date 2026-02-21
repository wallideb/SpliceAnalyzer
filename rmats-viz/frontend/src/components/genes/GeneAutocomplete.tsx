"use client";

/**
 * GeneAutocomplete
 * =================
 * An input component with live autocomplete backed by the Ensembl API.
 *
 * Features:
 * - Debounced search (350 ms) to limit API calls while the user types
 * - Dropdown suggestion list in "Symbol (ENSGXXXXXXXX)" format
 * - Keyboard navigation: ArrowUp/ArrowDown to move, Enter to select,
 *   Escape to close, Backspace on empty input removes last tag
 * - Displays selected genes as amber tags with a remove button
 * - Graceful error handling: shows a warning if Ensembl is unreachable
 *
 * Usage:
 * ```tsx
 * <GeneAutocomplete value={mutatedGenes} onChange={setMutatedGenes} />
 * ```
 */

import {
  KeyboardEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import type { GeneEntry } from "@/types/gene";
import { searchGenes } from "@/lib/api/genes";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface GeneAutocompleteProps {
  /** Currently selected genes. */
  value: GeneEntry[];
  /** Called whenever the gene list changes. */
  onChange: (genes: GeneEntry[]) => void;
}

// ---------------------------------------------------------------------------
// Debounce hook
// ---------------------------------------------------------------------------

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function GeneAutocomplete({ value, onChange }: GeneAutocompleteProps) {
  const [inputValue, setInputValue] = useState("");
  const [suggestions, setSuggestions] = useState<GeneEntry[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const [isLoading, setIsLoading] = useState(false);
  const [searchError, setSearchError] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLUListElement>(null);
  const debouncedQuery = useDebounce(inputValue.trim(), 350);

  // ── Fetch suggestions ───────────────────────────────────────────────────

  useEffect(() => {
    if (debouncedQuery.length < 2) {
      setSuggestions([]);
      setIsOpen(false);
      setSearchError(false);
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    setSearchError(false);

    searchGenes(debouncedQuery)
      .then((results) => {
        if (cancelled) return;
        // Filter out already-selected genes
        const selected = new Set(value.map((g) => g.ensembl_id));
        setSuggestions(results.filter((g) => !selected.has(g.ensembl_id)));
        setIsOpen(true);
        setHighlightedIndex(-1);
      })
      .catch(() => {
        if (cancelled) return;
        setSearchError(true);
        setSuggestions([]);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [debouncedQuery, value]);

  // ── Selection helpers ───────────────────────────────────────────────────

  const selectGene = useCallback(
    (gene: GeneEntry) => {
      if (!value.find((g) => g.ensembl_id === gene.ensembl_id)) {
        onChange([...value, gene]);
      }
      setInputValue("");
      setSuggestions([]);
      setIsOpen(false);
      setHighlightedIndex(-1);
      inputRef.current?.focus();
    },
    [value, onChange],
  );

  const removeGene = useCallback(
    (ensemblId: string) => {
      onChange(value.filter((g) => g.ensembl_id !== ensemblId));
    },
    [value, onChange],
  );

  // ── Keyboard navigation ─────────────────────────────────────────────────

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      setIsOpen(false);
      return;
    }

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightedIndex((i) => Math.min(i + 1, suggestions.length - 1));
      return;
    }

    if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightedIndex((i) => Math.max(i - 1, -1));
      return;
    }

    if (e.key === "Enter") {
      e.preventDefault();
      if (highlightedIndex >= 0 && suggestions[highlightedIndex]) {
        selectGene(suggestions[highlightedIndex]);
      }
      return;
    }

    if (e.key === "Backspace" && !inputValue && value.length > 0) {
      onChange(value.slice(0, -1));
    }
  };

  // ── Close on outside click ──────────────────────────────────────────────

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        inputRef.current &&
        !inputRef.current.contains(e.target as Node) &&
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <div className="relative">
      {/* Tag input area */}
      <div
        className="flex flex-wrap gap-1.5 border border-border rounded-lg px-3 py-2 bg-background min-h-[42px] cursor-text focus-within:ring-2 focus-within:ring-blue-500 dark:focus-within:ring-blue-400 transition-shadow"
        onClick={() => inputRef.current?.focus()}
      >
        {/* Selected gene tags */}
        {value.map((gene) => (
          <span
            key={gene.ensembl_id}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300 border border-amber-200 dark:border-amber-700"
          >
            <span>{gene.display}</span>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                removeGene(gene.ensembl_id);
              }}
              className="hover:text-amber-600 dark:hover:text-amber-200 transition-colors"
              aria-label={`Retirer ${gene.symbol}`}
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="w-3 h-3"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2.5}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </span>
        ))}

        {/* Text input */}
        <div className="relative flex-1 min-w-[140px] flex items-center">
          <input
            ref={inputRef}
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => suggestions.length > 0 && setIsOpen(true)}
            placeholder={value.length === 0 ? "Rechercher un gène (ex: BRCA1, TP53…)" : ""}
            className="w-full text-sm bg-transparent text-foreground placeholder:text-muted-foreground outline-none"
            autoComplete="off"
            spellCheck={false}
            aria-autocomplete="list"
            aria-expanded={isOpen}
          />
          {/* Loading spinner */}
          {isLoading && (
            <span className="absolute right-0 text-muted-foreground">
              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
                />
              </svg>
            </span>
          )}
        </div>
      </div>

      {/* Dropdown suggestions */}
      {isOpen && suggestions.length > 0 && (
        <ul
          ref={dropdownRef}
          className="absolute z-50 mt-1 w-full bg-card text-card-foreground border border-border rounded-lg shadow-xl overflow-hidden"
          role="listbox"
        >
          {suggestions.map((gene, idx) => (
            <li
              key={gene.ensembl_id}
              role="option"
              aria-selected={idx === highlightedIndex}
              onMouseDown={(e) => {
                // Prevent blur before click registers
                e.preventDefault();
                selectGene(gene);
              }}
              onMouseEnter={() => setHighlightedIndex(idx)}
              className={`px-3 py-2 text-sm cursor-pointer flex items-center justify-between gap-2 ${
                idx === highlightedIndex
                  ? "bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300"
                  : "text-foreground hover:bg-muted"
              }`}
            >
              <span className="font-semibold">{gene.symbol}</span>
              <span className="text-xs text-muted-foreground font-mono">{gene.ensembl_id}</span>
            </li>
          ))}
        </ul>
      )}

      {/* No results message */}
      {isOpen && suggestions.length === 0 && !isLoading && debouncedQuery.length >= 2 && (
        <div className="absolute z-50 mt-1 w-full bg-card text-card-foreground border border-border rounded-lg shadow-xl px-3 py-2 text-sm text-muted-foreground">
          Aucun gène trouvé pour &quot;{debouncedQuery}&quot;
        </div>
      )}

      {/* Ensembl API error */}
      {searchError && (
        <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
          Impossible de joindre Ensembl. Vérifiez votre connexion.
        </p>
      )}

      {/* Helper text */}
      <p className="text-xs text-muted-foreground mt-1">
        Tapez au moins 2 caractères pour afficher les suggestions Ensembl. Utilisez{" "}
        <kbd className="px-1 py-0.5 rounded bg-muted text-xs font-mono">↑↓</kbd> pour naviguer
        et <kbd className="px-1 py-0.5 rounded bg-muted text-xs font-mono">Entrée</kbd> pour sélectionner.
      </p>
    </div>
  );
}
