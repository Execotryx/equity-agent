"""Data layer: market data, SEC risk factors and web search behind one cache.

Importing this package loads yfinance, edgartools and tavily (about 10 s together), so do it at start-up.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from equity_agent.cache import DEFAULT_CACHE_PATH, Cache
from equity_agent.config import Settings
from equity_agent.data import fixtures, market, search, sec
from equity_agent.data.market import (
    DataError,
    InvalidTicker,
    MarketData,
    NotSupported,
    ProviderError,
    TickerNotFound,
    normalize_ticker,
)
from equity_agent.data.search import SearchData
from equity_agent.data.sec import SecData

__all__ = [
    "DataError",
    "DataLayer",
    "InvalidTicker",
    "MarketData",
    "NotSupported",
    "ProviderError",
    "SearchData",
    "SecData",
    "TickerNotFound",
    "normalize_ticker",
]


@dataclass
class DataLayer:
    cache: Cache
    market: MarketData
    sec: SecData
    search: SearchData

    @classmethod
    def live(cls, settings: Settings, cache_path: Path | None = DEFAULT_CACHE_PATH) -> DataLayer:
        sec.configure(settings.edgar_identity)
        cache = Cache(cache_path)
        return cls(
            cache=cache,
            market=MarketData(cache, market.YahooSource()),
            sec=SecData(cache, sec.EdgarSource(settings.edgar_identity)),
            search=SearchData(cache, search.TavilySource(settings.tavily_api_key)),
        )

    @classmethod
    def recorded(cls, directory: Path = fixtures.FIXTURES_DIR, cache_path: Path | None = None) -> DataLayer:
        """Fixture-backed data with no network access (tests and the offline demo)."""
        cache = Cache(cache_path)
        return cls(
            cache=cache,
            market=MarketData(cache, fixtures.FixtureMarketSource(directory)),
            sec=SecData(cache, fixtures.FixtureFilingSource(directory)),
            search=SearchData(cache, fixtures.FixtureSearchSource(directory)),
        )

    def close(self) -> None:
        self.sec.stop_parser()
        self.cache.close()
