/**
 * Shared formatting helpers for damage cost display (UI + PDF) and
 * backend-served upload asset URLs.
 */

import { BACKEND_BASE_URL } from "@/lib/api";

/**
 * Normalize any frame/snapshot path the pipeline emits (relative, already
 * `uploads/`-prefixed, or absolute on-disk containing `uploads/`) into the
 * relative `uploads/...` path the backend serves.
 */
export function uploadPath(path: unknown): string | null {
  if (typeof path !== "string" || !path) return null;
  return path.startsWith("uploads/")
    ? path
    : `uploads/${path.replace(/^.*uploads\//, "")}`;
}

/**
 * Full image `src` for an upload artifact, or null when there is none.
 */
export function uploadSrc(path?: string | null): string | null {
  const normalized = uploadPath(path);
  if (!normalized) return null;
  return `${BACKEND_BASE_URL}/${normalized}`;
}

export const SEVERITY_RANK: Record<string, number> = { low: 1, medium: 2, high: 3 };

export interface CostRange {
  low: number;
  high: number;
  midpoint?: number | null;
  currency?: string | null;
}

export function formatCurrency(amount: number, currency?: string | null): string {
  const code = (currency || "JPY").toUpperCase();
  try {
    return new Intl.NumberFormat("ja-JP", {
      style: "currency",
      currency: code,
      maximumFractionDigits: 0,
      minimumFractionDigits: 0,
    }).format(Math.round(amount));
  } catch {
    return `${code} ${Math.round(amount)}`;
  }
}

export function formatRange(cost: CostRange): string {
  const currency = cost.currency || "JPY";
  if (cost.low === cost.high) return formatCurrency(cost.low, currency);
  return `${formatCurrency(cost.low, currency)} – ${formatCurrency(cost.high, currency)}`;
}
