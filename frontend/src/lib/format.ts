// Number formatting, mirroring backend/src/equity_agent/formatting.py so the page and the agents' inputs agree.

import type { Multiples } from "./events";

export type MetricKey = keyof Multiples;

export const MISSING = "—";

export const METRIC_LABELS: Record<MetricKey, string> = {
  pe_ttm: "P/E (ttm)",
  pe_fwd: "Forward P/E",
  ev_ebitda: "EV/EBITDA",
  ev_revenue: "EV/Revenue",
  price_to_book: "P/B",
  net_margin: "Net margin",
  roe: "ROE",
  revenue_growth: "Revenue growth",
  debt_to_equity: "Debt/Equity",
  dividend_yield: "Dividend yield",
};

// Valuation multiples are only meaningful when positive (negative earnings make P/E meaningless).
const POSITIVE_ONLY = new Set<string>(["pe_ttm", "pe_fwd", "ev_ebitda", "ev_revenue", "price_to_book"]);
const PERCENT_METRICS = new Set<string>(["net_margin", "roe", "revenue_growth", "dividend_yield"]);

export function metricLabel(metric: string): string {
  return METRIC_LABELS[metric as MetricKey] ?? metric;
}

export function meaningful(metric: string, value: number | null | undefined): number | null {
  if (value === null || value === undefined || Number.isNaN(value)) return null;
  if (POSITIVE_ONLY.has(metric) && value <= 0) return null;
  return value;
}

/** The one text form of a metric value: "27.6%", "0.78" (debt/equity), "34.8", or "—". */
export function metricText(metric: string, value: number | null | undefined): string {
  const v = meaningful(metric, value);
  if (v === null) return MISSING;
  if (PERCENT_METRICS.has(metric)) return `${(v * 100).toFixed(1)}%`;
  return metric === "debt_to_equity" ? v.toFixed(2) : v.toFixed(1);
}

/** Compact money: "$4.82T", "$391.04B", "-$12.50M", "$212.43". */
export function money(value: number | null | undefined, currency = "USD"): string {
  if (value === null || value === undefined || Number.isNaN(value)) return MISSING;
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  const symbol = currency === "USD" ? "$" : `${currency} `;
  for (const [threshold, suffix] of [
    [1e12, "T"],
    [1e9, "B"],
    [1e6, "M"],
  ] as const) {
    if (abs >= threshold) return `${sign}${symbol}${(abs / threshold).toFixed(2)}${suffix}`;
  }
  return `${sign}${symbol}${abs.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** A fraction as a signed whole percent: 0.123 -> "+12%". */
export function pctChange(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return MISSING;
  const pct = Math.round(value * 100);
  return `${pct > 0 ? "+" : pct < 0 ? "−" : "±"}${Math.abs(pct)}%`;
}

/** A fraction as a plain percent: 0.62 -> "62%". */
export function percent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return MISSING;
  return `${(value * 100).toFixed(digits)}%`;
}

/** Milliseconds as seconds with one decimal: 8400 -> "8.4 s". */
export function seconds(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return MISSING;
  return `${(ms / 1000).toFixed(1)} s`;
}

export function usd(value: number): string {
  return `$${value.toFixed(value < 0.01 ? 4 : 3)}`;
}
