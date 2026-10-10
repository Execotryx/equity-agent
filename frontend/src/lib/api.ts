// Where the API lives and what a ticker looks like (the same rule as the backend's normalize_ticker).

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export const QUICK_PICKS = ["AAPL", "NVDA", "JPM", "COST", "TSLA"] as const;

const TICKER_PATTERN = /^[A-Z][A-Z0-9._\-]{0,9}$/;

/** The upper-cased ticker, or null when the input can't be one. */
export function normalizeTicker(raw: string): string | null {
  const ticker = raw.trim().toUpperCase();
  return TICKER_PATTERN.test(ticker) ? ticker : null;
}

export function streamUrl(ticker: string, refresh: boolean): string {
  const params = new URLSearchParams({ ticker });
  if (refresh) params.set("refresh", "true");
  return `${API_URL}/api/research/stream?${params}`;
}
