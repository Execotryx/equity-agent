"""Offline regressions for the instrument-identity checks used by the live KASE matrix."""

import pytest
from kase_cases import NATIVE_CASES, SHARES_SOURCE, USD_NATIVE_CASES, USD_US_LISTING_CASES, US_LISTING_CASES, quote_checks

from equity_agent.data import normalize_ticker

from equity_agent.models import Multiples, Quote, Snapshot


def quote(ticker: str, name: str, currency: str) -> Quote:
    return Quote(snapshot=Snapshot(ticker=ticker, name=name, currency=currency, price=100), multiples=Multiples())


def failed_checks(checks):
    return {check.criterion for check in checks if not check.passed}


def test_kaspi_nasdaq_quote_cannot_pass_as_kase_ordinary_share():
    case = next(case for case in NATIVE_CASES if case.kase_ticker == "KSPI")
    checks = quote_checks(case, quote("KSPI", "Joint Stock Company Kaspi.kz", "USD"), "NasdaqGS")
    assert failed_checks(checks) == {"expected quote currency", "expected trading venue"}


def test_currency_alone_does_not_prove_kase_venue():
    checks = quote_checks(NATIVE_CASES[0], quote("HSBK", "Halyk Bank", "KZT"), "London")
    assert failed_checks(checks) == {"expected trading venue"}


def test_an_unrelated_company_with_the_same_symbol_is_rejected():
    checks = quote_checks(NATIVE_CASES[0], quote("HSBK", "Unrelated Bank", "KZT"), "KASE")
    assert failed_checks(checks) == {"expected company"}


def test_unknown_venue_is_not_assumed_to_be_kase():
    checks = quote_checks(NATIVE_CASES[0], quote("HSBK", "Halyk Bank", "KZT"), "")
    assert failed_checks(checks) == {"expected trading venue"}


@pytest.mark.parametrize("case", US_LISTING_CASES, ids=lambda case: case.id)
def test_explicit_us_listing_has_separate_identity(case):
    venue = "NYSE" if case.input_ticker == "JPM" else "NasdaqGS"
    checks = quote_checks(case, quote(case.input_ticker, case.company, "USD"), venue)
    assert not failed_checks(checks)
    assert case.kase_ticker != case.input_ticker


def test_usd_does_not_make_a_nasdaq_quote_a_kase_quote():
    case = USD_NATIVE_CASES[1]
    checks = quote_checks(case, quote("KSPID", "Kaspi.kz", "USD"), "NasdaqGS")
    assert failed_checks(checks) == {"expected trading venue"}


@pytest.mark.parametrize("case", USD_NATIVE_CASES[:3], ids=lambda case: case.id)
def test_depositary_receipt_suffix_survives_normalization(case):
    assert normalize_ticker(case.kase_ticker) == case.input_ticker
    assert case.input_ticker.endswith("D")
    assert case.input_ticker != case.kase_ticker[:-1].upper()


@pytest.mark.parametrize("case", USD_US_LISTING_CASES, ids=lambda case: case.id)
def test_usd_issuer_alias_uses_shares_listing_evidence(case):
    assert case.source == SHARES_SOURCE
    assert not failed_checks(quote_checks(case, quote(case.input_ticker, case.company, "USD"), "NasdaqGS"))


@pytest.mark.parametrize("case", USD_NATIVE_CASES[-2:], ids=lambda case: case.id)
def test_underscore_kase_symbols_reach_native_provider(case, monkeypatch):
    from equity_agent.data import kase
    import test_kase_live
    from test_kase_adapter import instrument
    from test_kase_live import observe

    calls = []
    def native(ticker):
        calls.append(ticker)
        return instrument(ticker)
    monkeypatch.setattr(test_kase_live, "live_source", lambda: kase.RoutedSource(fetch=native))
    # Disable enrichment explicitly to keep this routing regression offline.
    monkeypatch.setattr(kase.YahooSource, "info", lambda _: {})
    observed, venue, checks = observe(case)
    assert calls == [case.input_ticker]
    if case.input_ticker == "CORE_KZ":
        assert observed is None and checks[0].detail == "quote unavailable"
    else:
        assert observed is not None and venue == "KASE" and not failed_checks(checks)
