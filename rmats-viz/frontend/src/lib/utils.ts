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
