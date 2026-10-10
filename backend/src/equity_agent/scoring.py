"""Deterministic comps valuation and the five-factor scorecard (IMPLEMENTATION_PLAN.md §4.4–4.5).

Pure functions: no network, no LLM. The same inputs always give the same table, scores and signal.
Demo: `uv run python -m equity_agent.scoring AAPL MSFT GOOGL DELL [--offline]`.
"""

from __future__ import annotations

import re
import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from equity_agent.config import ScoringConfig
from equity_agent.data.kase import issuer_key
from equity_agent.formatting import METRIC_LABELS, MISSING, meaningful, metric_text, pct_change
from equity_agent.models import (
    CompRow,
    CompsTable,
    FactorScore,
    MetricSet,
    Multiples,
    PeerBatch,
    PeerExclusion,
    PeerOrigin,
    PricePoint,
    Quote,
    Scorecard,
    Signal,
)

DEFAULT_SCORING = ScoringConfig()

METRIC_SETS: dict[MetricSet, list[str]] = {
    "general": ["pe_ttm", "pe_fwd", "ev_ebitda", "ev_revenue", "net_margin", "revenue_growth", "debt_to_equity"],
    "financials": ["pe_ttm", "pe_fwd", "price_to_book", "roe", "dividend_yield", "revenue_growth"],
    "real_estate": ["pe_ttm", "price_to_book", "dividend_yield", "ev_revenue"],
}
SHARE_CLASS_PAIRS = [{"GOOG", "GOOGL"}, {"BRK-A", "BRK-B"}, {"FOX", "FOXA"}, {"NWS", "NWSA"}]
_NAME_SUFFIX = re.compile(
    r"\b(class [a-c]|inc|incorporated|corp|corporation|co|company|plc|ltd|limited|holdings?|group|the|n\.?v|s\.?a|ag)\b\.?"
)

# ---- metric sets and medians ----------------------------------------------------------------------------------


def metric_set_for(sector: str | None) -> MetricSet:
    if sector == "Financial Services":
        return "financials"
    if sector == "Real Estate":
        return "real_estate"
    return "general"


def primary_metric(metric_set: MetricSet, target: Multiples) -> str:
    if metric_set == "financials":
        return "price_to_book"
    if metric_set == "real_estate":
        return "pe_ttm"
    return "pe_fwd" if meaningful("pe_fwd", target.pe_fwd) is not None else "pe_ttm"


def median_of(metric: str, peers: Iterable[Multiples]) -> float | None:
    values = [v for p in peers if (v := meaningful(metric, getattr(p, metric))) is not None]
    return statistics.median(values) if values else None


def pct_vs(value: float | None, median: float | None) -> float | None:
    if value is None or median is None or median <= 0:
        return None
    return value / median - 1


# ---- peer eligibility -----------------------------------------------------------------------------------------


def _company_key(name: str) -> str:
    cleaned = _NAME_SUFFIX.sub(" ", name.lower().replace(",", " ").replace("&", " and "))
    return " ".join(cleaned.split())


def _same_company(a: Quote, b: Quote) -> bool:
    if issuer_key(a.snapshot.ticker) == issuer_key(b.snapshot.ticker):
        return True
    tickers = {a.snapshot.ticker, b.snapshot.ticker}
    if any(tickers == pair for pair in SHARE_CLASS_PAIRS):
        return True
    return _company_key(a.snapshot.name) == _company_key(b.snapshot.name)


@dataclass
class PeerSelection:
    included: list[Quote]
    exclusions: list[PeerExclusion]


def select_peers(
    target: Quote,
    candidates: Sequence[str],
    quotes: Mapping[str, Quote],
    failures: Mapping[str, str],
    config: ScoringConfig = DEFAULT_SCORING,
) -> PeerSelection:
    """Apply eligibility in candidate order: equity with a price, not the target, not a second share class.

    `quotes` holds valid quotes by ticker; `failures` holds the data layer's reason for the others.
    At most `max_peers` are included; later eligible candidates are left out silently.
    """
    included: list[Quote] = []
    exclusions: list[PeerExclusion] = []
    for ticker in dict.fromkeys(candidates):
        quote = quotes.get(ticker)
        if issuer_key(ticker) == issuer_key(target.snapshot.ticker):
            exclusions.append(PeerExclusion(ticker=ticker, reason="is the target"))
        elif quote is None:
            exclusions.append(PeerExclusion(ticker=ticker, reason=failures.get(ticker, "no data")))
        elif not quote.snapshot.price:
            exclusions.append(PeerExclusion(ticker=ticker, reason="no price"))
        elif _same_company(quote, target) or any(_same_company(quote, other) for other in included):
            exclusions.append(PeerExclusion(ticker=ticker, reason="duplicate share class"))
        elif len(included) < config.max_peers:
            included.append(quote)
    return PeerSelection(included=included, exclusions=exclusions)


# ---- comps table ----------------------------------------------------------------------------------------------


def _row(quote: Quote, is_target: bool = False) -> CompRow:
    snap = quote.snapshot
    return CompRow(
        ticker=snap.ticker,
        name=snap.name,
        market_cap=snap.market_cap,
        multiples=quote.multiples,
        is_target=is_target,
        sector=snap.sector,
        industry=snap.industry,
        business_summary=snap.business_summary,
    )


def build_comps_table(
    target: Quote,
    selection: PeerSelection,
    *,
    rationales: Mapping[str, str] | None = None,
    origin: Mapping[str, PeerOrigin] | None = None,
    sources: Sequence[str] = (),
    config: ScoringConfig = DEFAULT_SCORING,
) -> CompsTable:
    metric_set = metric_set_for(target.snapshot.sector)
    metrics = METRIC_SETS[metric_set]
    peer_multiples = [q.multiples for q in selection.included]
    median = Multiples(**{field: median_of(field, peer_multiples) for field in Multiples.model_fields})
    target_values = target.multiples
    peers = [q.snapshot.ticker for q in selection.included]
    return CompsTable(
        metric_set=metric_set,
        metrics=metrics,
        primary_metric=primary_metric(metric_set, target_values),
        rows=[_row(target, is_target=True), *(_row(q) for q in selection.included)],
        median=median,
        target_vs_median_pct={
            m: pct_vs(meaningful(m, getattr(target_values, m)), getattr(median, m)) for m in metrics
        },
        peer_rationales={t: r for t, r in (rationales or {}).items() if t in peers},
        peer_origin={t: (origin or {}).get(t, "agent") for t in peers},
        exclusions=selection.exclusions,
        sources=list(sources),
        insufficient=len(selection.included) < config.min_peers,
    )


def assemble_comps(
    target: Quote,
    tickers: Sequence[str],
    batch: PeerBatch,
    *,
    rationales: Mapping[str, str] | None = None,
    origin: Mapping[str, PeerOrigin] | None = None,
    sources: Sequence[str] = (),
    config: ScoringConfig = DEFAULT_SCORING,
) -> CompsTable:
    """Eligibility then table, from an already-fetched peer batch: the one path from candidate tickers to a table."""
    selection = select_peers(target, tickers, batch.quotes, batch.failed, config)
    return build_comps_table(target, selection, rationales=rationales, origin=origin, sources=sources, config=config)


# ---- scorecard ------------------------------------------------------------------------------------------------

INSUFFICIENT = "insufficient data"


def moving_average(prices: Sequence[PricePoint], window: int) -> float | None:
    if len(prices) < window:
        return None
    return statistics.fmean(p.close for p in prices[-window:])


def range_position(price: float, low: float | None, high: float | None) -> float | None:
    """0 at the 52-week low, 1 at the high."""
    if low is None or high is None or high <= low:
        return None
    return (price - low) / (high - low)


def _banded(diff: float, band: float, higher_is_better: bool) -> int:
    diff = round(diff, 9)  # "more than 15 %": a value exactly on the band edge (e.g. 25.5 / 30 - 1) scores 0
    if diff > band:
        return 1 if higher_is_better else -1
    if diff < -band:
        return -1 if higher_is_better else 1
    return 0


def score_valuation(table: CompsTable, config: ScoringConfig) -> FactorScore:
    metric = table.primary_metric
    target = meaningful(metric, getattr(table.target.multiples, metric))
    median = getattr(table.median, metric)
    diff = pct_vs(target, median)
    if diff is None or target is None or median is None:
        return FactorScore(name="valuation", score=0, detail=INSUFFICIENT)
    score = _banded(diff, config.valuation_band, higher_is_better=False)
    label = METRIC_LABELS[metric]
    return FactorScore(
        name="valuation",
        score=score,  # type: ignore[arg-type]
        detail=f"{label} {metric_text(metric, target)} vs peer median {metric_text(metric, median)} ({diff * 100:+.0f}%; band ±{config.valuation_band * 100:.0f}%)",
    )


def _points_factor(name: str, metric: str, table: CompsTable, band: float) -> FactorScore:
    target = getattr(table.target.multiples, metric)
    median = getattr(table.median, metric)
    if target is None or median is None:
        return FactorScore(name=name, score=0, detail=INSUFFICIENT)  # type: ignore[arg-type]
    diff = target - median
    score = _banded(diff, band, higher_is_better=True)
    return FactorScore(
        name=name,  # type: ignore[arg-type]
        score=score,  # type: ignore[arg-type]
        detail=f"{METRIC_LABELS[metric]} {metric_text(metric, target)} vs peer median {metric_text(metric, median)} "
        f"({diff * 100:+.1f} pts; band ±{band * 100:.0f} pts)",
    )


def score_upside(quote: Quote, config: ScoringConfig) -> FactorScore:
    target, price = quote.analyst_target_mean, quote.snapshot.price
    if target is None or not price:
        return FactorScore(name="analyst_upside", score=0, detail=INSUFFICIENT)
    upside = target / price - 1
    return FactorScore(
        name="analyst_upside",
        score=_banded(upside, config.upside_band, higher_is_better=True),  # type: ignore[arg-type]
        detail=f"mean analyst target {target:.2f} vs price {price:.2f} ({upside * 100:+.1f}%; band ±{config.upside_band * 100:.0f}%)",
    )


def score_momentum(quote: Quote, prices: Sequence[PricePoint], config: ScoringConfig) -> FactorScore:
    snap = quote.snapshot
    average = moving_average(prices, config.momentum_window)
    position = range_position(snap.price, snap.week52_low, snap.week52_high)
    if average is None or position is None:
        return FactorScore(name="momentum", score=0, detail=INSUFFICIENT)
    above = snap.price > average
    upper = position >= 0.5
    score = 1 if above and upper else -1 if not above and not upper else 0
    return FactorScore(
        name="momentum",
        score=score,  # type: ignore[arg-type]
        detail=f"price {snap.price:.2f} {'above' if above else 'below'} its {config.momentum_window}-day average "
        f"{average:.2f}; at {position * 100:.0f}% of the 52-week range",
    )


def signal_for(total: int, config: ScoringConfig = DEFAULT_SCORING) -> Signal:
    if total >= config.buy_at:
        return "BUY"
    if total <= config.sell_at:
        return "SELL"
    return "HOLD"


def build_scorecard(
    target: Quote, table: CompsTable | None, prices: Sequence[PricePoint], config: ScoringConfig = DEFAULT_SCORING
) -> Scorecard:
    """Score the five factors. Without a comps table, the three peer-relative factors score 0 (insufficient data)."""
    if table is None or not table.peers:
        relative = [FactorScore(name=n, score=0, detail=INSUFFICIENT) for n in ("valuation", "growth", "profitability")]  # type: ignore[misc]
    else:
        margin_metric = "roe" if table.metric_set == "financials" else "net_margin"
        relative = [
            score_valuation(table, config),
            _points_factor("growth", "revenue_growth", table, config.growth_band),
            _points_factor("profitability", margin_metric, table, config.profitability_band),
        ]
    factors = [*relative, score_upside(target, config), score_momentum(target, prices, config)]
    total = sum(f.score for f in factors)
    return Scorecard(factors=factors, total=total, preliminary_signal=signal_for(total, config))


def scorecard_lines(card: Scorecard) -> list[str]:
    """The scorecard as printed by the command-line tools."""
    lines = [f"  {f.name:<15} {f.score:+d}  {f.detail}" for f in card.factors]
    return [*lines, f"  total {card.total:+d} -> preliminary signal {card.preliminary_signal}"]


# ---- demo command ---------------------------------------------------------------------------------------------


def _print_table(table: CompsTable) -> None:
    header = ["Ticker", *(METRIC_LABELS[m] for m in table.metrics)]
    print(f"metric set: {table.metric_set}; primary: {METRIC_LABELS[table.primary_metric]}")
    print("  " + " | ".join(f"{h:>14}" for h in header))

    def cells(values: Multiples) -> list[str]:
        out = []
        for m in table.metrics:
            out.append(metric_text(m, getattr(values, m)) or MISSING)
        return out

    for row in table.rows:
        print("  " + " | ".join(f"{c:>14}" for c in [row.ticker + ("*" if row.is_target else ""), *cells(row.multiples)]))
    print("  " + " | ".join(f"{c:>14}" for c in ["median", *cells(table.median)]))
    vs = [pct_change(table.target_vs_median_pct[m]) or MISSING for m in table.metrics]
    print("  " + " | ".join(f"{c:>14}" for c in ["target vs med", *vs]))
    for e in table.exclusions:
        print(f"  excluded {e.ticker}: {e.reason}")


def main(argv: list[str] | None = None) -> int:
    import argparse

    from equity_agent.config import load_settings
    from equity_agent.data import DataError, DataLayer, normalize_ticker

    parser = argparse.ArgumentParser(description="Print the comps table and scorecard for a target and peers.")
    parser.add_argument("target")
    parser.add_argument("peers", nargs="+")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)
    data = DataLayer.recorded() if args.offline else DataLayer.live(load_settings())
    try:
        ticker = normalize_ticker(args.target)
        target = data.market.quote(ticker).value
        history = data.market.history(ticker).value
        peers = [normalize_ticker(p) for p in args.peers]
        table = assemble_comps(target, peers, data.market.peers(peers).value, origin=dict.fromkeys(peers, "user"))
        _print_table(table)
        print("\n".join(scorecard_lines(build_scorecard(target, table, history.prices))))
    except DataError as error:
        print(error)
        return 1
    finally:
        data.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
