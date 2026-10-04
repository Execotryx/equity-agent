import sys
import time

import pytest

from equity_agent.cache import Cache
from equity_agent.data import DataLayer
from equity_agent.data.fixtures import FixtureMarketSource
from equity_agent.data.market import (
    InvalidTicker,
    MarketData,
    NotSupported,
    TickerNotFound,
    normalize_ticker,
    QUOTE_FIELDS,
    parse_quote,
)


@pytest.fixture
def data() -> DataLayer:
    return DataLayer.recorded()


@pytest.mark.parametrize(("raw", "expected"), [(" aapl ", "AAPL"), ("brk.b", "BRK-B"), ("BRK-B", "BRK-B")])
def test_normalize_ticker(raw, expected):
    assert normalize_ticker(raw) == expected


@pytest.mark.parametrize("raw", ["$$$", "", "   ", "1ABC", "TOOLONGTICKER"])
def test_malformed_ticker_rejected(raw):
    with pytest.raises(InvalidTicker):
        normalize_ticker(raw)


def test_aapl_snapshot(data):
    quote = data.market.quote("AAPL").value
    snap = quote.snapshot
    assert snap.price > 0 and (snap.market_cap or 0) > 0
    assert snap.sector == "Technology"
    assert 0 < len(snap.business_summary) <= 600
    assert quote.multiples.pe_fwd is not None and quote.analyst_target_mean is not None


def test_percent_fields_are_fractions(data):
    multiples = data.market.quote("JPM").value.multiples
    assert multiples.dividend_yield is not None and 0 < multiples.dividend_yield < 0.2


def test_bank_has_no_ev_ebitda(data):
    multiples = data.market.quote("JPM").value.multiples
    assert multiples.ev_ebitda is None
    assert multiples.pe_ttm is not None and multiples.price_to_book is not None


def test_unknown_ticker(data):
    with pytest.raises(TickerNotFound, match="ticker not found"):
        data.market.quote("ZZZZQX")


def test_non_equity_rejected():
    with pytest.raises(NotSupported, match="only individual stocks"):
        parse_quote("SPY", {"quoteType": "ETF", "regularMarketPrice": 500.0})


def test_missing_fields_are_none_not_zero():
    quote = parse_quote("X", {"quoteType": "EQUITY", "currentPrice": 10.0, "longName": "X Corp"})
    assert quote.snapshot.market_cap is None
    assert all(value is None for value in quote.multiples.model_dump().values())


def test_history_for_cost(data):
    history = data.market.history("COST").value
    assert len(history.revenue) >= 3
    assert len(history.prices) >= 240
    assert [p.date for p in history.prices] == sorted(p.date for p in history.prices)
    assert [y.year for y in history.revenue] == sorted(y.year for y in history.revenue)


def test_peer_batch_reports_failures(data):
    batch = data.market.peers(["MSFT", "GOOGL", "ZZZZQX"]).value
    assert list(batch.quotes) == ["MSFT", "GOOGL"]
    assert batch.failed == {"ZZZZQX": "ticker not found"}


class SlowSource(FixtureMarketSource):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def info(self, ticker):
        self.calls += 1
        time.sleep(0.2)
        return super().info(ticker)


def test_peer_batch_runs_concurrently():
    market = MarketData(Cache(None), SlowSource())
    start = time.perf_counter()
    batch = market.peers(["MSFT", "GOOGL", "DELL", "HPQ", "SONY"]).value
    assert len(batch.quotes) == 5
    assert time.perf_counter() - start < 0.2 * 5 * 0.6


def test_quote_cached_within_ttl():
    source = SlowSource()
    market = MarketData(Cache(None), source)
    market.quote("AAPL")
    second = market.quote("AAPL")
    assert second.hit and source.calls == 1


def test_peer_cache_hits_reported():
    market = MarketData(Cache(None), FixtureMarketSource())
    market.peers(["MSFT"])
    hits = market.peers(["MSFT", "GOOGL"]).hits
    assert hits == ["quote:MSFT"]


def test_provider_libraries_load_with_the_data_layer():
    assert {"yfinance", "edgar", "tavily"} <= set(sys.modules)


def test_reasons_are_stable_and_shared(data, monkeypatch):
    from equity_agent.data.market import DataError

    monkeypatch.setattr(DataError, "__str__", lambda self: "reworded message")
    with pytest.raises(TickerNotFound) as caught:
        data.market.quote("ZZZZQX")
    assert caught.value.reason == "ticker not found" and caught.value.ticker == "ZZZZQX"
    batch = data.market.peers(["MSFT", "ZZZZQX"]).value
    assert batch.failed == {"ZZZZQX": "ticker not found"}


class BrokenSource(FixtureMarketSource):
    def info(self, ticker):
        raise ConnectionError("yahoo down")


def test_provider_failure_becomes_provider_error():
    from equity_agent.data.market import ProviderError

    market = MarketData(Cache(None), BrokenSource())
    with pytest.raises(ProviderError) as caught:
        market.quote("AAPL")
    assert caught.value.reason == "provider error" and caught.value.detail == "ConnectionError"
    batch = market.peers(["MSFT"]).value
    assert batch.failed == {"MSFT": "provider error"}


def test_every_recorded_quote_parses_with_declared_fields():
    import json

    from equity_agent.data.fixtures import FIXTURES_DIR

    paths = sorted(FIXTURES_DIR.glob("*/info.json"))
    assert len(paths) >= 30
    for path in paths:
        info = json.loads(path.read_text(encoding="utf-8"))
        assert set(info) <= set(QUOTE_FIELDS), path.parent.name
        parse_quote(path.parent.name, info)


def test_undeclared_field_read_fails():
    from equity_agent.data.market import DeclaredFields

    with pytest.raises(KeyError, match="not declared"):
        DeclaredFields({"beta": 1.2}).get("beta")
