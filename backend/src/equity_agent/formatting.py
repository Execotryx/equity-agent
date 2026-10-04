"""Metric definitions and every text rendering of numbers, used by scoring, agent inputs and printed views.

One rendering per metric: percent-like metrics as "27.6%", debt-to-equity as "0.78", other multiples as "34.8", and
non-meaningful values (a negative P/E) as missing.
"""

from __future__ import annotations

METRIC_LABELS = {
    "pe_ttm": "P/E (ttm)",
    "pe_fwd": "Forward P/E",
    "ev_ebitda": "EV/EBITDA",
    "ev_revenue": "EV/Revenue",
    "price_to_book": "P/B",
    "net_margin": "Net margin",
    "roe": "ROE",
    "revenue_growth": "Revenue growth",
    "debt_to_equity": "Debt/Equity",
    "dividend_yield": "Dividend yield",
}
# Valuation multiples are only meaningful when positive (negative earnings make P/E meaningless).
POSITIVE_ONLY = {"pe_ttm", "pe_fwd", "ev_ebitda", "ev_revenue", "price_to_book"}
PERCENT_METRICS = {"net_margin", "roe", "revenue_growth", "dividend_yield"}
MISSING = "—"


def meaningful(metric: str, value: float | None) -> float | None:
    if value is None or (metric in POSITIVE_ONLY and value <= 0):
        return None
    return value


def metric_text(metric: str, value: float | None) -> str | None:
    """The one text form of a metric value, or None when it is missing or not meaningful."""
    value = meaningful(metric, value)
    if value is None:
        return None
    if metric in PERCENT_METRICS:
        return f"{value * 100:.1f}%"
    return f"{value:.2f}" if metric == "debt_to_equity" else f"{value:.1f}"


def money(value: float | None, currency: str = "USD") -> str | None:
    if value is None:
        return None
    sign = "-" if value < 0 else ""
    value = abs(value)
    symbol = "$" if currency == "USD" else f"{currency} "
    for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if value >= threshold:
            return f"{sign}{symbol}{value / threshold:.2f}{suffix}"
    return f"{sign}{symbol}{value:,.2f}"


def pct_change(value: float | None) -> str | None:
    return None if value is None else f"{value * 100:+.0f}%"


def truncate_words(text: str, limit: int) -> str:
    """At most `limit` characters, cut at a word boundary and marked with an ellipsis."""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0] + "…"
