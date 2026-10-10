"""Offline native-quote, cross-listing and currency regressions using recorded KASE responses."""

import asyncio
import io
import json
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

from equity_agent.agents.agents import build_profile
from equity_agent.agents.payloads import profile_payload
from equity_agent.cache import Cache
from equity_agent.data import DataLayer
from equity_agent.data import kase
from equity_agent.data.market import (
    InvalidTicker, MarketData, ProviderError, QuoteUnavailable, TickerNotFound, UnsupportedInstrument,
    normalize_ticker, parse_quote,
)
from equity_agent.models import History, Multiples, Quote, Snapshot, YearValue
from equity_agent.scoring import select_peers
from fakes import collect_events, fake_services
from equity_agent.pipeline import report_from_event

FIXTURES = Path(__file__).parent / "fixtures" / "kase_native"


def instrument(ticker):
    return json.loads((FIXTURES / f"{ticker}.json").read_text(encoding="utf-8"))


class AliasSource:
    def __init__(self, native="FRHC_KZ", currency: str | None = "USD"):
        self.mapping = kase.MAPPINGS[native]
        self.currency = currency
        self.calls = []
        self.fail = False

    def info(self, ticker):
        self.calls.append(("info", ticker))
        if self.fail:
            raise TimeoutError("fixture failure")
        return {
            "symbol": ticker, "quoteType": "EQUITY", "longName": self.mapping.issuer_names[-1],
            "currency": "USD", "financialCurrency": self.currency, "currentPrice": 100,
            "marketCap": 1000, "trailingPE": 20, "forwardPE": 15, "priceToBook": 2,
            "dividendYield": 4, "targetMeanPrice": 120, "enterpriseToEbitda": 8,
            "enterpriseToRevenue": 3, "fiftyTwoWeekLow": 50, "fiftyTwoWeekHigh": 150,
            "profitMargins": .1, "returnOnEquity": .2, "revenueGrowth": .15, "debtToEquity": 70,
            "sector": "Financial Services", "industry": "Banks", "longBusinessSummary": "Issuer description.",
        }

    def income(self, ticker) -> dict[str, dict[str, float | None]]:
        self.calls.append(("income", ticker))
        if self.fail:
            raise TimeoutError()
        return {"Total Revenue": {"2025-12-31": 1000}, "Net Income": {"2025-12-31": 100}}

    def closes(self, ticker):
        raise AssertionError("alias trading history must never be requested for KASE")


def source(native="FRHC_KZ", currency: str | None = "USD"):
    yahoo = AliasSource(native, currency)
    return kase.RoutedSource(yahoo, instrument), yahoo


@pytest.mark.parametrize(("raw", "expected"), [
    (" frhc_kz ", "FRHC_KZ"), ("kspid", "KSPID"), ("brk.b", "BRK-B"),
    ("BRK-B", "BRK-B"), ("A_12345678", "A_12345678"),
])
def test_ticker_boundaries_and_existing_share_classes(raw, expected):
    assert normalize_ticker(raw) == expected


@pytest.mark.parametrize("raw", ["_FRHC", "FRHC/KZ", "FRHC KZ", "A_123456789", "1_A", "A$B"])
def test_ticker_invalid_characters_and_lengths(raw):
    with pytest.raises(InvalidTicker):
        normalize_ticker(raw)


@pytest.mark.parametrize("ticker", list(kase.MAPPINGS))
def test_recorded_native_identity_units_and_routing(ticker):
    routed, yahoo = source(ticker)
    quote = parse_quote(ticker, routed.info(ticker))
    assert quote.snapshot.price == instrument(ticker)["price"]
    assert quote.snapshot.quote_provenance is not None and quote.enrichment_provenance is not None
    assert quote.snapshot.quote_provenance.provider == "KASE"
    assert quote.snapshot.quote_provenance.source_symbol == instrument(ticker)["code"]
    assert quote.snapshot.quote_provenance.timestamp == instrument(ticker)["date0"]
    assert quote.enrichment_provenance.native_isin in kase.MAPPINGS[ticker].isins
    assert quote.enrichment_provenance.native_shares_per_unit == (40 if ticker == "HSBKD" else 1)
    assert quote.enrichment_provenance.source_shares_per_unit == (40 if ticker == "HSBKD" else 1)
    assert yahoo.calls == [("info", kase.MAPPINGS[ticker].alias)]
    assert routed.closes(ticker) == []
    assert quote.snapshot.week52_low is None and quote.snapshot.week52_high is None
    assert quote.multiples.ev_ebitda is None and quote.multiples.ev_revenue is None


@pytest.mark.parametrize("price", [None, 0, -1, float("nan"), float("inf")])
def test_recognized_without_positive_finite_price_never_uses_close_or_alias(price):
    raw = instrument("CORE_KZ")
    raw.update(price=price, close_price=999, bid=998, offer=1000)
    routed = kase.RoutedSource(fetch=lambda _: raw)
    with pytest.raises(QuoteUnavailable):
        routed.info("CORE_KZ")


@pytest.mark.parametrize("field,value", [("code", "OTHER_KZ"), ("org_name_en", "Wrong Issuer"),
                                         ("ticker", {}), ("date0", 123), ("currency_type", None)])
def test_malformed_and_mismatched_identity_rejected(field, value):
    raw = instrument("FRHC_KZ")
    raw[field] = value
    with pytest.raises(ProviderError):
        kase.RoutedSource(fetch=lambda _: raw).info("FRHC_KZ")


@pytest.mark.parametrize("field,value", [("currency_type", "KZT"), ("sec_type", "bond")])
def test_unsupported_instrument_or_currency(field, value):
    raw = instrument("FRHC_KZ")
    raw[field] = value
    with pytest.raises(UnsupportedInstrument):
        kase.RoutedSource(fetch=lambda _: raw).info("FRHC_KZ")


def test_preferred_share_rejected():
    raw = instrument("FRHC_KZ")
    raw["ticker"]["typesec_en"] = "preferred"
    with pytest.raises(UnsupportedInstrument):
        kase.RoutedSource(fetch=lambda _: raw).info("FRHC_KZ")


@pytest.mark.parametrize("ticker", ["HSBKD", "KSPID", "KZAPD"])
def test_receipt_requires_receipt_isin_not_underlying_common_share(ticker):
    raw = instrument(ticker)
    raw["ticker"]["nind"] = raw["ticker"]["nin"]
    raw["ticker"]["nind2"] = ""
    with pytest.raises(ProviderError):
        kase.RoutedSource(fetch=lambda _: raw).info(ticker)


def test_http_request_timeout_symbol_and_response_cleanup(monkeypatch):
    response = io.BytesIO(json.dumps(instrument("FRHC_KZ")).encode())
    def open_request(request, *, timeout):
        assert request.full_url == kase.API_ROOT + "FRHC_KZ/"
        assert timeout == 10
        return response
    monkeypatch.setattr(kase, "urlopen", open_request)
    assert kase.fetch_instrument("FRHC_KZ")["code"] == "FRHC_KZ"
    assert response.closed


@pytest.mark.parametrize("error,expected", [
    (HTTPError(kase.API_ROOT, 404, "missing", Message(), None), TickerNotFound),
    (HTTPError(kase.API_ROOT, 503, "outage", Message(), None), ProviderError),
    (TimeoutError(), ProviderError), (URLError("offline"), ProviderError),
])
def test_http_unknown_timeout_and_outage_are_distinct(monkeypatch, error, expected):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(kase, "urlopen", fail)
    with pytest.raises(expected):
        kase.fetch_instrument("UNKNOWN_KZ")


@pytest.mark.parametrize("body", [b"not json", b"[]", b"null"])
def test_malformed_http_response(monkeypatch, body):
    monkeypatch.setattr(kase, "urlopen", lambda *args, **kwargs: io.BytesIO(body))
    with pytest.raises(ProviderError):
        kase.fetch_instrument("FRHC_KZ")


def test_valuation_and_usd_cap_target_adjustments():
    routed, _ = source()
    quote = parse_quote("FRHC_KZ", routed.info("FRHC_KZ"))
    ratio = quote.snapshot.price / 100
    assert quote.multiples.pe_ttm == pytest.approx(20 * ratio)
    assert quote.multiples.pe_fwd == pytest.approx(15 * ratio)
    assert quote.multiples.price_to_book == pytest.approx(2 * ratio)
    assert quote.multiples.dividend_yield == pytest.approx(.04 / ratio)
    assert quote.snapshot.market_cap == pytest.approx(1000 * ratio)
    assert quote.analyst_target_mean == 120
    assert quote.enrichment_provenance is not None and quote.enrichment_provenance.analyst_target_basis is not None
    assert "Cross-listing estimate" in quote.enrichment_provenance.analyst_target_basis


@pytest.mark.parametrize("ticker", ["HSBKD", "KZAPD", "KSPID"])
def test_non_usd_accounts_preserve_currency_and_private_alias_verbatim(ticker):
    routed, yahoo = source(ticker, "KZT")
    market = MarketData(Cache(None), routed)
    quote = market.quote(ticker).value
    history = market.history(ticker).value
    profile = build_profile(quote, history)
    assert profile.financial_currency == "KZT" and profile.snapshot.currency == "USD"
    assert quote.multiples.pe_ttm is None and quote.multiples.pe_fwd is None
    assert quote.multiples.price_to_book is None and quote.multiples.dividend_yield is None
    assert quote.multiples.roe == .2 and quote.multiples.debt_to_equity == .7
    assert profile.price_history == []
    assert quote.analyst_target_mean == 120  # Halyk's native and alias GDRs both represent 40 shares.
    assert ("income", kase.MAPPINGS[ticker].alias) in yahoo.calls
    assert profile_payload(profile)["revenue_by_fiscal_year"] == {"2025": "KZT 1,000.00"}


def test_unknown_financial_currency_omits_history_even_if_passed_to_builder():
    routed, _ = source(currency=None)
    quote = parse_quote("FRHC_KZ", routed.info("FRHC_KZ"))
    profile = build_profile(quote, History(revenue=[YearValue(year=2025, value=1000)]))
    assert profile.revenue_history == [] and profile_payload(profile)["revenue_by_fiscal_year"] == {}
    assert any("currency unknown" in warning for warning in quote.diagnostics)


def test_enrichment_outage_retains_native_quote_and_diagnostic():
    routed, yahoo = source()
    yahoo.fail = True
    quote = parse_quote("FRHC_KZ", routed.info("FRHC_KZ"))
    assert quote.snapshot.price == instrument("FRHC_KZ")["price"]
    assert quote.enrichment_provenance is None
    assert any("enrichment unavailable" in warning for warning in quote.diagnostics)
    assert all(value is None for value in quote.multiples.model_dump().values())


def test_wrong_alias_identity_cannot_enrich(monkeypatch):
    routed, yahoo = source()
    original = yahoo.info
    monkeypatch.setattr(yahoo, "info", lambda ticker: {**original(ticker), "longName": "Unrelated Issuer"})
    quote = parse_quote("FRHC_KZ", routed.info("FRHC_KZ"))
    assert quote.snapshot.price == instrument("FRHC_KZ")["price"] and quote.enrichment_provenance is None


def test_no_inferred_alias_for_unmapped_kase_symbol():
    raw = instrument("CORE_KZ")
    raw["price"] = 10
    quote = parse_quote("CORE_KZ", kase.RoutedSource(fetch=lambda _: raw).info("CORE_KZ"))
    assert quote.enrichment_provenance is None and quote.snapshot.name == raw["org_name_en"]


def test_native_alias_cache_isolation_normalization_and_refresh():
    routed, yahoo = source()
    market = MarketData(Cache(None), routed)
    native = market.quote(" frhc_kz ")
    alias = market.quote("FRHC")
    assert native.value.snapshot.price != alias.value.snapshot.price
    assert market.quote("FRHC_KZ").hits == ["quote:FRHC_KZ"]
    assert market.quote("FRHC").hits == ["quote:FRHC"]
    before = len(yahoo.calls)
    market.quote("FRHC_KZ", refresh=True)
    assert len(yahoo.calls) == before + 1


@pytest.mark.parametrize("native", list(kase.MAPPINGS))
def test_mapped_alias_excluded_even_when_names_differ_or_quote_missing(native):
    alias = kase.MAPPINGS[native].alias.replace(".", "-")
    target = Quote(snapshot=Snapshot(ticker=native, name="KASE issuer", price=10), multiples=Multiples())
    selected = select_peers(target, [alias], {}, {alias: "provider error"})
    assert not selected.included and selected.exclusions[0].reason == "is the target"


def test_pipeline_preserves_native_identity_uses_sec_alias_and_caches_report(monkeypatch):
    data = DataLayer.recorded()
    routed, _ = source()
    data.market = MarketData(data.cache, routed)
    filings = []
    original = data.sec.risk_headings
    def headings(ticker, **kwargs):
        filings.append(ticker)
        return original("AAPL", **kwargs)
    monkeypatch.setattr(data.sec, "risk_headings", headings)
    services = fake_services(data=data)
    report = report_from_event(collect_events(services, " frhc_kz ")[-1])
    assert report.ticker == "FRHC_KZ" and report.financials.snapshot.ticker == "FRHC_KZ"
    assert filings == ["FRHC"] and report.financials.price_history == []
    assert any("momentum is neutral" in warning for warning in report.quality_warnings)
    monkeypatch.setattr(routed, "info", lambda _: pytest.fail("cached report must avoid all providers"))
    cached_events = collect_events(services, "frhc_kz")
    assert cached_events[-1].event == "report" and cached_events[-1].data["from_cache"]


def test_native_shared_run_key_retains_underscore():
    from equity_agent.streaming import RunRegistry
    async def run():
        data = DataLayer.recorded()
        routed, _ = source()
        data.market = MarketData(data.cache, routed)
        registry = RunRegistry(fake_services(data=data))
        first = registry.subscribe(" frhc_kz ")
        second = registry.subscribe("FRHC_KZ")
        left = [event async for event in first]
        right = [event async for event in second]
        assert registry.started == 1 and left[-1].data["ticker"] == right[-1].data["ticker"] == "FRHC_KZ"
        await registry.close()
        data.close()
    asyncio.run(run())


def test_api_sse_and_report_lookup_preserve_native_symbol():
    from test_api_research import api, stream
    data = DataLayer.recorded()
    routed, _ = source()
    data.market = MarketData(data.cache, routed)
    with api(fake_services(data=data)) as client:
        events = stream(client, " frhc_kz ")
        assert events[-1][0] == "report" and events[-1][1]["ticker"] == "FRHC_KZ"
        response = client.get("/api/research/frhc_kz")
        assert response.status_code == 200 and response.json()["ticker"] == "FRHC_KZ"
        assert response.json()["financials"]["snapshot"]["quote_provenance"]["provider"] == "KASE"


@pytest.mark.parametrize("case", json.loads((FIXTURES / "failure_cases.json").read_text(encoding="utf-8")),
                         ids=lambda case: case["id"])
def test_failure_protocol_fixtures(case, monkeypatch):
    from equity_agent.data.market import DataError
    def request(*args, **kwargs):
        if case.get("exception"):
            raise TimeoutError()
        if case.get("status"):
            raise HTTPError(kase.API_ROOT, case["status"], "fixture", Message(), io.BytesIO(b"{}"))
        raw = instrument("FRHC_KZ")
        if "override" in case:
            raw.update(case["override"])
        else:
            raw = case["body"]
        return io.BytesIO(json.dumps(raw).encode())
    monkeypatch.setattr(kase, "urlopen", request)
    with pytest.raises(DataError) as error:
        kase.RoutedSource(fetch=kase.fetch_instrument).info("FRHC_KZ")
    assert error.value.reason == case["reason"]


def test_recording_roundtrip_preserves_native_origin_currency_and_private_alias(tmp_path):
    from equity_agent.demo import Recording, RecordingMarketSource
    from equity_agent.data.fixtures import FixtureMarketSource
    routed, yahoo = source("HSBKD", "KZT")
    market = MarketData(Cache(None), RecordingMarketSource(routed, Recording(tmp_path)))
    quote, history = market.quote("HSBKD").value, market.history("HSBKD").value
    replay = MarketData(Cache(None), FixtureMarketSource(tmp_path))
    assert replay.quote("HSBKD").value == quote
    assert replay.history("HSBKD").value == history
    assert quote.enrichment_provenance is not None and quote.enrichment_provenance.source_symbol == "HSBK.IL"
    assert ("income", "HSBK.IL") in yahoo.calls


def test_non_us_sec_mapping_omits_lookup(monkeypatch):
    from equity_agent.models import StageError
    data = DataLayer.recorded()
    routed, _ = source("HSBKD", "KZT")
    data.market = MarketData(data.cache, routed)
    monkeypatch.setattr(data.sec, "risk_headings", lambda *args, **kwargs: pytest.fail("no verified US issuer mapping"))
    report = report_from_event(collect_events(fake_services(data=data), "HSBKD")[-1])
    assert isinstance(report.risks, StageError) and "No verified SEC issuer mapping" in report.risks.message


def test_target_alias_is_excluded_before_peer_provider_requests():
    from equity_agent.data.fixtures import FixtureMarketSource
    from equity_agent.models import CompsTable, PeerPick, PeerPicks
    from fakes import FakeClaude
    yahoo = AliasSource()
    fixtures = FixtureMarketSource()
    original = yahoo.info
    yahoo.info = lambda ticker: original(ticker) if ticker == "FRHC" else fixtures.info(ticker)
    data = DataLayer.recorded()
    data.market = MarketData(data.cache, kase.RoutedSource(yahoo, instrument))
    picks = PeerPicks(peers=[PeerPick(ticker=t, name=t) for t in ["FRHC", "MSFT", "GOOGL", "NVDA"]])
    report = report_from_event(collect_events(fake_services(FakeClaude({"comps": [picks]}), data), "FRHC_KZ")[-1])
    assert yahoo.calls.count(("info", "FRHC")) == 1
    assert isinstance(report.comps, CompsTable) and "FRHC" not in [peer.ticker for peer in report.comps.peers]
    assert any(exclusion.ticker == "FRHC" and exclusion.reason == "is the target" for exclusion in report.comps.exclusions)


def test_income_enrichment_failure_degrades_history_without_changing_native_quote(monkeypatch):
    routed, yahoo = source()
    def unavailable(ticker):
        raise TimeoutError("fixture income failure")
    monkeypatch.setattr(yahoo, "income", unavailable)
    data = DataLayer.recorded()
    data.market = MarketData(data.cache, routed)
    report = report_from_event(collect_events(fake_services(data=data), "FRHC_KZ")[-1])
    assert report.financials.snapshot.price == instrument("FRHC_KZ")["price"]
    assert not report.financials.revenue_history
    assert any("financial history unavailable" in warning for warning in report.quality_warnings)


def test_legacy_unknown_currency_cannot_be_inferred_from_usd_trading_price():
    from equity_agent.models import FinancialProfile
    quote = Quote(snapshot=Snapshot(ticker="OLD", name="Legacy issuer", currency="USD", price=10), multiples=Multiples())
    assert not build_profile(quote, History(revenue=[YearValue(year=2025, value=1000)])).revenue_history
    legacy = FinancialProfile(snapshot=quote.snapshot, multiples=quote.multiples,
                              revenue_history=[YearValue(year=2025, value=1000)], ebitda_history=[],
                              net_income_history=[], price_history=[])
    assert profile_payload(legacy)["revenue_by_fiscal_year"] == {}
    assert profile_payload(legacy)["financial_history_note"] == "Reporting currency unknown; monetary history omitted."


@pytest.mark.parametrize("field,value", [("symbol", "OTHER"), ("longName", "Freedom Unrelated Corp."),
                                         ("currency", "KZT"), ("isin", "US0000000000")])
def test_alias_identity_and_currency_failures_cannot_replace_native_price(monkeypatch, field, value):
    routed, yahoo = source()
    original = yahoo.info
    monkeypatch.setattr(yahoo, "info", lambda ticker: {**original(ticker), field: value})
    quote = parse_quote("FRHC_KZ", routed.info("FRHC_KZ"))
    assert quote.snapshot.price == instrument("FRHC_KZ")["price"] and quote.enrichment_provenance is None


@pytest.mark.parametrize("shares", [0, -1, float("nan"), float("inf")])
def test_unverified_units_prevent_enrichment_and_valuation(monkeypatch, shares):
    from dataclasses import replace
    monkeypatch.setitem(kase.MAPPINGS, "FRHC_KZ", replace(kase.MAPPINGS["FRHC_KZ"], alias_shares=shares))
    routed, _ = source()
    quote = parse_quote("FRHC_KZ", routed.info("FRHC_KZ"))
    assert quote.snapshot.price == instrument("FRHC_KZ")["price"]
    assert quote.multiples.pe_ttm is None and quote.snapshot.market_cap is None
    assert quote.analyst_target_mean is None and quote.enrichment_provenance is None


def test_quote_only_solidcore_identity_is_verified_before_quote_availability():
    raw = instrument("CORE_KZ")
    raw["ticker"]["nin"] = "JE0000000000"
    with pytest.raises(ProviderError):
        kase.RoutedSource(fetch=lambda _: raw).info("CORE_KZ")


def test_unknown_account_currency_preserves_independent_yahoo_price_history(monkeypatch):
    data = DataLayer.recorded()
    original = data.market.source.info
    def info(ticker):
        raw = original(ticker)
        return {**raw, "financialCurrency": None} if ticker == "AAPL" else raw
    monkeypatch.setattr(data.market.source, "info", info)
    report = report_from_event(collect_events(fake_services(data=data), "AAPL")[-1])
    assert not report.financials.revenue_history
    assert len(report.financials.price_history) >= 240
    assert any("currency unknown" in warning for warning in report.quality_warnings)


@pytest.mark.parametrize("native_price,alias_price", [(168.55, 1e-308), (1e-300, 1e308), (168.55, None)])
def test_invalid_equivalent_price_ratio_cannot_create_valuation_or_lose_unit_based_target(monkeypatch, native_price, alias_price):
    raw = instrument("FRHC_KZ")
    raw["price"] = native_price
    yahoo = AliasSource()
    original = yahoo.info
    monkeypatch.setattr(yahoo, "info", lambda ticker: {**original(ticker), "currentPrice": alias_price})
    quote = parse_quote("FRHC_KZ", kase.RoutedSource(yahoo, lambda _: raw).info("FRHC_KZ"))
    assert quote.snapshot.price == native_price and quote.multiples.pe_ttm is None
    assert quote.multiples.dividend_yield is None and quote.snapshot.market_cap is None
    assert quote.analyst_target_mean == 120
    assert any("Price-sensitive valuation metrics unavailable" in warning for warning in quote.diagnostics)
