"""Market data from Yahoo Finance: ticker validation, quote, history and concurrent peer batches.

yfinance is imported at module level on purpose: it takes several seconds to import, and that cost must be paid at
service start-up, not inside the first request.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any, ClassVar, Protocol, TypeVar

import yfinance as yf

from equity_agent.cache import HISTORY_TTL, QUOTE_TTL, Cache
from equity_agent.formatting import truncate_words
from equity_agent.models import Fetched, History, Multiples, PeerBatch, PricePoint, Quote, Snapshot, YearValue

T = TypeVar("T")

TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
SUMMARY_CHARS = 600
PEER_WORKERS = 5


class DataError(Exception):
    """A request that cannot be served. `reason` is a fixed, user-facing text; the message adds the specifics.

    Callers show `reason`, never parse the message.
    """

    reason: ClassVar[str] = "data unavailable"

    def __init__(self, ticker: str | None = None, detail: str | None = None) -> None:
        self.ticker = ticker
        self.detail = detail
        super().__init__(self.reason + (f": {ticker}" if ticker else "") + (f" ({detail})" if detail else ""))


class InvalidTicker(DataError):
    reason = "invalid ticker"


class TickerNotFound(DataError):
    reason = "ticker not found"


class NotSupported(DataError):
    reason = "only individual stocks are supported"


class ProviderError(DataError):
    reason = "provider error"


def normalize_ticker(raw: str) -> str:
    """Upper-case, trim and convert a class-share dot to Yahoo's hyphen (`brk.b` -> `BRK-B`)."""
    ticker = (raw or "").strip().upper()
    if not TICKER_PATTERN.match(ticker):
        raise InvalidTicker(repr(raw))
    return ticker.replace(".", "-")


def try_normalize_ticker(raw: str) -> str | None:
    """`normalize_ticker`, or None for input that is not a ticker (for checking model output)."""
    try:
        return normalize_ticker(raw)
    except InvalidTicker:
        return None


class MarketSource(Protocol):
    """Raw provider access. `YahooSource` is the live one; tests and offline mode read recorded JSON."""

    def info(self, ticker: str) -> dict[str, Any]: ...

    def income(self, ticker: str) -> dict[str, dict[str, float | None]]:
        """Income statement rows ("Total Revenue", "EBITDA", "Net Income") -> {ISO period end: value}."""
        ...

    def closes(self, ticker: str) -> list[tuple[str, float]]:
        """One year of daily closes as (ISO date, close), oldest first."""
        ...


INCOME_ROWS = ("Total Revenue", "EBITDA", "Net Income")


def _clean(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


class YahooSource:
    def info(self, ticker: str) -> dict[str, Any]:
        return dict(yf.Ticker(ticker).info or {})

    def income(self, ticker: str) -> dict[str, dict[str, float | None]]:
        frame = yf.Ticker(ticker).income_stmt
        rows: dict[str, dict[str, float | None]] = {}
        if frame is None or frame.empty:
            return rows
        for row in INCOME_ROWS:
            if row in frame.index:
                rows[row] = {str(col)[:10]: _clean(frame.at[row, col]) for col in frame.columns}
        return rows

    def closes(self, ticker: str) -> list[tuple[str, float]]:
        frame = yf.Ticker(ticker).history(period="1y", interval="1d", auto_adjust=True)
        if frame is None or frame.empty:
            return []
        closes: list[tuple[str, float]] = []
        for idx, close in frame["Close"].items():
            value = _clean(close)
            if value is not None:
                closes.append((str(idx)[:10], value))  # Timestamp text starts with the ISO date
        return closes


# Every provider field parse_quote reads. The fixture recorder records exactly these, and reading any other field
# raises, so a new field can't be used without being recorded for the offline tests.
QUOTE_FIELDS = (
    "quoteType", "longName", "shortName", "sector", "industry", "currency", "currentPrice", "regularMarketPrice",
    "marketCap", "fiftyTwoWeekLow", "fiftyTwoWeekHigh", "longBusinessSummary", "trailingPE", "forwardPE",
    "enterpriseToEbitda", "enterpriseToRevenue", "priceToBook", "profitMargins", "returnOnEquity", "revenueGrowth",
    "debtToEquity", "dividendYield", "targetMeanPrice", "recommendationKey",
)  # fmt: skip


class DeclaredFields:
    """Read access to a raw quote limited to QUOTE_FIELDS."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.raw = raw

    def get(self, key: str) -> Any:
        if key not in QUOTE_FIELDS:
            raise KeyError(f"quote field {key!r} is not declared in QUOTE_FIELDS")
        return self.raw.get(key)


def parse_quote(ticker: str, raw: dict[str, Any]) -> Quote:
    """Validate and normalise a raw quote. Raises TickerNotFound or NotSupported."""
    info = DeclaredFields(raw)
    quote_type = info.get("quoteType")
    price = _clean(info.get("currentPrice")) or _clean(info.get("regularMarketPrice"))
    if quote_type is None or (quote_type == "EQUITY" and not price):
        raise TickerNotFound(ticker)
    if quote_type != "EQUITY":
        raise NotSupported(ticker, f"{ticker} is {str(quote_type).lower()}")
    assert price is not None

    def pct(key: str) -> float | None:  # Yahoo reports these two in percent
        value = _clean(info.get(key))
        return None if value is None else value / 100

    summary = truncate_words((info.get("longBusinessSummary") or "").strip(), SUMMARY_CHARS)
    snapshot = Snapshot(
        ticker=ticker,
        name=info.get("longName") or info.get("shortName") or ticker,
        sector=info.get("sector"),
        industry=info.get("industry"),
        currency=info.get("currency") or "USD",
        price=price,
        market_cap=_clean(info.get("marketCap")),
        week52_low=_clean(info.get("fiftyTwoWeekLow")),
        week52_high=_clean(info.get("fiftyTwoWeekHigh")),
        business_summary=summary,
    )
    multiples = Multiples(
        pe_ttm=_clean(info.get("trailingPE")),
        pe_fwd=_clean(info.get("forwardPE")),
        ev_ebitda=_clean(info.get("enterpriseToEbitda")),
        ev_revenue=_clean(info.get("enterpriseToRevenue")),
        price_to_book=_clean(info.get("priceToBook")),
        net_margin=_clean(info.get("profitMargins")),
        roe=_clean(info.get("returnOnEquity")),
        revenue_growth=_clean(info.get("revenueGrowth")),
        debt_to_equity=pct("debtToEquity"),
        dividend_yield=pct("dividendYield"),
    )
    return Quote(
        snapshot=snapshot,
        multiples=multiples,
        analyst_target_mean=_clean(info.get("targetMeanPrice")),
        analyst_recommendation=info.get("recommendationKey"),
    )


def parse_history(income: dict[str, dict[str, float | None]], closes: list[tuple[str, float]]) -> History:
    def series(row: str) -> list[YearValue]:
        values = income.get(row, {})
        points = [YearValue(year=int(period[:4]), value=v) for period, v in values.items() if v is not None]
        return sorted(points, key=lambda p: p.year)[-4:]

    prices = sorted((PricePoint(date=date.fromisoformat(d), close=c) for d, c in closes), key=lambda p: p.date)
    return History(
        revenue=series("Total Revenue"),
        ebitda=series("EBITDA"),
        net_income=series("Net Income"),
        prices=prices,
    )


def from_provider(ticker: str, call: Callable[[], T]) -> T:
    """Run a provider call; any failure that isn't already a DataError becomes a ProviderError."""
    try:
        return call()
    except DataError:
        raise
    except Exception as error:  # noqa: BLE001 - provider libraries raise many unrelated exception types
        raise ProviderError(ticker, type(error).__name__) from error


class MarketData:
    def __init__(self, cache: Cache, source: MarketSource | None = None) -> None:
        self.cache = cache
        self.source: MarketSource = source or YahooSource()

    def quote(self, ticker: str, *, refresh: bool = False) -> Fetched[Quote]:
        """Validated snapshot and valuation inputs (15-minute cache). Raises a DataError for bad tickers."""
        return self.cache.fetch(
            f"quote:{ticker}",
            Quote,
            QUOTE_TTL,
            lambda: parse_quote(ticker, from_provider(ticker, lambda: self.source.info(ticker))),
            refresh=refresh,
        )

    def peer_quote(self, ticker: str, *, refresh: bool = False) -> Fetched[Quote]:
        """A peer's quote; the same as `quote` except in the offline demo, where only recorded targets are reports."""
        return MarketData.quote(self, ticker, refresh=refresh)

    def history(self, ticker: str, *, refresh: bool = False) -> Fetched[History]:
        """Up to 4 fiscal years of revenue, EBITDA and net income, plus 1 year of daily closes (24-hour cache)."""
        return self.cache.fetch(
            f"fin:{ticker}",
            History,
            HISTORY_TTL,
            lambda: from_provider(ticker, lambda: parse_history(self.source.income(ticker), self.source.closes(ticker))),
            refresh=refresh,
        )

    def peers(self, tickers: Sequence[str], *, refresh: bool = False) -> Fetched[PeerBatch]:
        """Fetch every candidate with at most PEER_WORKERS concurrent calls; report failed peers with a reason.

        Eligibility and the table's peer limit are applied by scoring, after all candidates have been considered.
        """
        tickers = list(dict.fromkeys(tickers))

        def one(ticker: str) -> Fetched[Quote] | str:
            try:
                return self.peer_quote(normalize_ticker(ticker), refresh=refresh)
            except DataError as error:
                return error.reason

        with ThreadPoolExecutor(max_workers=PEER_WORKERS) as pool:
            outcomes = list(pool.map(one, tickers))
        quotes: dict[str, Quote] = {}
        failed: dict[str, str] = {}
        hits: list[str] = []
        for ticker, outcome in zip(tickers, outcomes, strict=True):
            if isinstance(outcome, str):
                failed[ticker] = outcome
            else:
                quotes[outcome.value.snapshot.ticker] = outcome.value
                hits.extend(outcome.hits)
        return Fetched(PeerBatch(quotes=quotes, failed=failed), hits)
