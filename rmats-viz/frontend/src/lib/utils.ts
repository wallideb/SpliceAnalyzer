import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatFDR(fdr: number | null | undefined): string {
  if (fdr === null || fdr === undefined) return "N/A";
  if (fdr === 0) return "0";
  if (fdr < 0.0001) return fdr.toExponential(2);
  return fdr.toFixed(4);
}

export function formatDeltaPSI(diff: number | null | undefined): string {
  if (diff === null || diff === undefined) return "N/A";
  const sign = diff > 0 ? "+" : "";
  return `${sign}${diff.toFixed(3)}`;
}

export function formatCoord(val: number | null | undefined): string {
  if (val === null || val === undefined) return "N/A";
  return val.toLocaleString();
}

/** Splice-site position number for column index i, skipping zero if requested. */
export function posNum(i: number, start: number, skipZero: boolean): number {
  let pos = start + i;
  if (skipZero && pos >= 0) pos += 1;
  return pos;
}

/** Label string with sign for positive positions. */
export function posLabel(pos: number): string {
  return pos > 0 ? `+${pos}` : `${pos}`;
}
