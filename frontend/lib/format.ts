/**
 * Shared formatting helpers for damage cost display (UI + PDF).
 */

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
