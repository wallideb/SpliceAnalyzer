"use client";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import type { SplicingEvent } from "@/types/event";

export interface BasketItem {
  event: SplicingEvent;
  analysisId: string;
  analysisName: string;
  addedAt: string; // ISO date string
}

interface BasketContextType {
  items: BasketItem[];
  addItems: (newItems: BasketItem[]) => void;
  removeItem: (eventId: string) => void;
  hasItem: (eventId: string) => boolean;
  clearBasket: () => void;
  count: number;
}

const BasketContext = createContext<BasketContextType | null>(null);

const STORAGE_KEY = "spliceanalyzer_basket_v1";

export function BasketProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<BasketItem[]>([]);

  // Hydrate from localStorage once the component mounts (client-side only)
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) setItems(JSON.parse(raw) as BasketItem[]);
    } catch {
      // ignore parse errors
    }
  }, []);

  // Persist whenever items change
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
    } catch {
      // ignore storage errors (private browsing quota)
    }
  }, [items]);

  const addItems = useCallback((newItems: BasketItem[]) => {
    setItems((prev) => {
      const existingIds = new Set(prev.map((i) => i.event.id));
      const toAdd = newItems.filter((i) => !existingIds.has(i.event.id));
      return toAdd.length === 0 ? prev : [...prev, ...toAdd];
    });
  }, []);

  const removeItem = useCallback((eventId: string) => {
    setItems((prev) => prev.filter((i) => i.event.id !== eventId));
  }, []);

  const hasItem = useCallback(
    (eventId: string) => items.some((i) => i.event.id === eventId),
    [items]
  );

  const clearBasket = useCallback(() => setItems([]), []);

  return (
    <BasketContext.Provider
      value={{ items, addItems, removeItem, hasItem, clearBasket, count: items.length }}
    >
      {children}
    </BasketContext.Provider>
  );
}

export function useBasket(): BasketContextType {
  const ctx = useContext(BasketContext);
  if (!ctx) throw new Error("useBasket must be used within BasketProvider");
  return ctx;
}
