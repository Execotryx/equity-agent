from datetime import date, timedelta

import pytest

from equity_agent.config import ScoringConfig
from equity_agent.data import DataLayer
from equity_agent.models import CompsTable, Multiples, PricePoint, Quote, Snapshot
from equity_agent.scoring import (
    INSUFFICIENT,
    PeerSelection,
    build_comps_table,
    build_scorecard,
    median_of,
    metric_set_for,
    moving_average,
    pct_vs,
    primary_metric,
    range_position,
    select_peers,
    signal_for,
)


def quote(ticker: str, name: str | None = None, sector: str = "Technology", price: float = 100.0, target=None, low=50.0, high=150.0, **multiples) -> Quote:
    return Quote(
        snapshot=Snapshot(ticker=ticker, name=name or f"{ticker} Corp", sector=sector, price=price, week52_low=low, week52_high=high),
        multiples=Multiples(**multiples),
        analyst_target_mean=target,
    )


# ---- peer eligibility -----------------------------------------------------------------------------------------


def test_target_proposed_as_own_peer_excluded():
    target = quote("AAPL", "Apple Inc.")
    selection = select_peers(target, ["AAPL", "MSFT"], {"AAPL": target, "MSFT": quote("MSFT")}, {})
    assert [q.snapshot.ticker for q in selection.included] == ["MSFT"]
    assert [(e.ticker, e.reason) for e in selection.exclusions] == [("AAPL", "is the target")]


@pytest.mark.parametrize("value", [float("inf"), float("nan"), -float("inf")])
def test_nonfinite_medians_and_upside_are_neutral(value):
    assert median_of("revenue_growth", [Multiples(revenue_growth=value)]) is None
    card = build_scorecard(quote("EDGE", target=value), None, [])
    assert card.factors[3].score == 0 and card.factors[3].detail == INSUFFICIENT


def test_overflowed_derived_values_are_unavailable():
    assert pct_vs(1e308, 1e-308) is None
    assert median_of("pe_ttm", [Multiples(pe_ttm=1e308)] * 2) is None
    prices = [PricePoint(date=date(2025, 1, 1), close=1e308)] * 200
    assert moving_average(prices, 200) is None
    assert range_position(1e308, -1e308, 1e308) is None
    card = build_scorecard(quote("EDGE", price=1e-308, target=1e308), None, [])
    assert card.factors[3].score == 0


def test_duplicate_share_class_keeps_first():
    quotes = {"GOOGL": quote("GOOGL", "Alphabet Inc."), "GOOG": quote("GOOG", "Alphabet Inc.")}
    selection = select_peers(quote("MSFT"), ["GOOGL", "GOOG"], quotes, {})
    assert [q.snapshot.ticker for q in selection.included] == ["GOOGL"]
    assert selection.exclusions[0].reason == "duplicate share class"


def test_share_class_detected_by_name():
    quotes = {"FOXA": quote("FOXA", "Fox Corporation Class A"), "FOX": quote("FOX", "Fox Corporation Class B")}
    selection = select_peers(quote("DIS"), ["FOXA", "FOX"], quotes, {})
    assert len(selection.included) == 1


@pytest.mark.parametrize(("failure", "reason"), [("ticker not found", "ticker not found"), ("only individual stocks are supported (spy is etf)", "only individual stocks are supported (spy is etf)")])
def test_failed_candidates_carry_data_layer_reason(failure, reason):
    selection = select_peers(quote("AAPL"), ["X"], {}, {"X": failure})
    assert selection.exclusions[0].reason == reason


def test_no_price_excluded():
    selection = select_peers(quote("AAPL"), ["X"], {"X": quote("X", price=0.0)}, {})
    assert selection.exclusions[0].reason == "no price"


def test_too_few_eligible_peers_marked_insufficient():
    target = quote("AAPL")
    quotes = {t: quote(t) for t in ["A", "B"]}
    selection = select_peers(target, ["A", "B", "C", "D"], quotes, {"C": "ticker not found", "D": "ticker not found"})
    table = build_comps_table(target, selection)
    assert table.insufficient and len(table.peers) == 2 and len(table.exclusions) == 2


def test_more_than_five_eligible_uses_first_five():
    tickers = [f"P{i}" for i in range(7)]
    selection = select_peers(quote("AAPL"), tickers, {t: quote(t) for t in tickers}, {})
    assert [q.snapshot.ticker for q in selection.included] == tickers[:5]


# ---- metric sets ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sector", "expected"),
    [("Financial Services", "financials"), ("Real Estate", "real_estate"), ("Technology", "general"), (None, "general")],
)
def test_metric_set_for_sector(sector, expected):
    assert metric_set_for(sector) == expected


def test_primary_metric_falls_back_to_trailing_pe():
    assert primary_metric("general", Multiples(pe_fwd=20.0)) == "pe_fwd"
    assert primary_metric("general", Multiples(pe_ttm=20.0)) == "pe_ttm"
    assert primary_metric("general", Multiples(pe_fwd=-5.0, pe_ttm=20.0)) == "pe_ttm"
    assert primary_metric("financials", Multiples(pe_fwd=10.0)) == "price_to_book"
    assert primary_metric("real_estate", Multiples()) == "pe_ttm"


# ---- medians --------------------------------------------------------------------------------------------------


def test_median_ignores_missing():
    assert median_of("ev_ebitda", [Multiples(ev_ebitda=20.0), Multiples(), Multiples(ev_ebitda=30.0)]) == 25


def test_negative_pe_excluded_from_median():
    assert median_of("pe_ttm", [Multiples(pe_ttm=-4.0), Multiples(pe_ttm=10.0), Multiples(pe_ttm=20.0)]) == 15


def test_negative_margin_kept_in_median():
    assert median_of("net_margin", [Multiples(net_margin=-0.1), Multiples(net_margin=0.3)]) == pytest.approx(0.1)


def test_no_values_gives_missing_median():
    assert median_of("ev_ebitda", [Multiples(), Multiples()]) is None


def test_premium_to_peers():
    assert pct_vs(33.0, 30.0) == pytest.approx(0.10)
    assert pct_vs(10.0, 0.0) is None and pct_vs(None, 10.0) is None


# ---- comps table on fixtures ----------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def data() -> DataLayer:
    return DataLayer.recorded()


def table_for(data: DataLayer, target: str, peers: list[str]) -> CompsTable:
    target_quote = data.market.quote(target).value
    batch = data.market.peers(peers).value
    return build_comps_table(target_quote, select_peers(target_quote, peers, batch.quotes, batch.failed))


def test_aapl_general_table(data):
    table = table_for(data, "AAPL", ["MSFT", "GOOGL", "DELL", "HPQ"])
    assert table.metric_set == "general" and table.primary_metric == "pe_fwd"
    assert [r.ticker for r in table.rows] == ["AAPL", "MSFT", "GOOGL", "DELL", "HPQ"]
    assert table.rows[0].is_target and not table.insufficient
    assert set(table.target_vs_median_pct) == set(table.metrics)
    assert table.median.pe_fwd is not None


def test_jpm_financials_table(data):
    table = table_for(data, "JPM", ["BAC", "C", "WFC", "GS"])
    assert table.metric_set == "financials" and table.primary_metric == "price_to_book"
    assert "ev_ebitda" not in table.metrics


# ---- scorecard ------------------------------------------------------------------------------------------------


def make_table(target: Quote, peers: list[Quote]) -> CompsTable:
    return build_comps_table(target, PeerSelection(included=peers, exclusions=[]))


def prices(values: list[float]) -> list[PricePoint]:
    start = date(2025, 1, 1)
    return [PricePoint(date=start + timedelta(days=i), close=v) for i, v in enumerate(values)]


def factor(card, name):
    return next(f for f in card.factors if f.name == name)


PEERS = [quote(t, pe_fwd=30.0, revenue_growth=0.05, net_margin=0.10) for t in ("A", "B", "C")]


def test_expensive_but_fast_growing():
    target = quote("T", pe_fwd=42.0, revenue_growth=0.25, net_margin=0.10)
    card = build_scorecard(target, make_table(target, PEERS), [])
    valuation, growth = factor(card, "valuation"), factor(card, "growth")
    assert (valuation.score, growth.score) == (-1, 1)
    assert "42.0" in valuation.detail and "30.0" in valuation.detail and "+40%" in valuation.detail
    assert "25.0%" in growth.detail and "+20.0 pts" in growth.detail


@pytest.mark.parametrize(("pe", "score"), [(25.5, 0), (25.4, 1), (34.5, 0), (34.6, -1), (30.0, 0)])
def test_valuation_band_edges(pe, score):
    target = quote("T", pe_fwd=pe)
    assert factor(build_scorecard(target, make_table(target, PEERS), []), "valuation").score == score


@pytest.mark.parametrize(("growth", "score"), [(0.10, 0), (0.1001, 1), (0.0, 0), (-0.0001, -1)])
def test_growth_band_edges(growth, score):
    target = quote("T", revenue_growth=growth)
    assert factor(build_scorecard(target, make_table(target, PEERS), []), "growth").score == score


def test_profitability_uses_roe_for_banks():
    bank_peers = [quote(t, sector="Financial Services", roe=0.10, price_to_book=1.5) for t in ("A", "B", "C")]
    target = quote("JPM", sector="Financial Services", roe=0.18, net_margin=0.0, price_to_book=2.5)
    card = build_scorecard(target, make_table(target, bank_peers), [])
    assert factor(card, "profitability").score == 1 and "ROE" in factor(card, "profitability").detail
    assert factor(card, "valuation").score == -1


@pytest.mark.parametrize(("target_price", "score"), [(110.0, 0), (110.1, 1), (90.0, 0), (89.9, -1)])
def test_upside_band_edges(target_price, score):
    card = build_scorecard(quote("T", target=target_price), None, [])
    assert factor(card, "analyst_upside").score == score


def test_missing_analyst_target():
    upside = factor(build_scorecard(quote("T"), None, []), "analyst_upside")
    assert (upside.score, upside.detail) == (0, INSUFFICIENT)


def test_momentum_up_down_and_mixed():
    rising = prices([50.0] * 100 + [100.0] * 100)  # 200-day average 75
    assert factor(build_scorecard(quote("T", price=140.0), None, rising), "momentum").score == 1
    assert factor(build_scorecard(quote("T", price=60.0), None, rising), "momentum").score == -1
    assert factor(build_scorecard(quote("T", price=80.0), None, rising), "momentum").score == 0  # above avg, lower half


def test_momentum_needs_200_days():
    assert factor(build_scorecard(quote("T", price=140.0), None, prices([1.0] * 199)), "momentum").detail == INSUFFICIENT


def test_helpers():
    assert moving_average(prices([1.0, 2.0, 3.0]), 2) == 2.5
    assert range_position(75.0, 50.0, 100.0) == 0.5 and range_position(1.0, None, 2.0) is None


def test_no_comps_scores_relative_factors_zero():
    card = build_scorecard(quote("T", pe_fwd=10.0), None, [])
    assert all(factor(card, n).detail == INSUFFICIENT for n in ("valuation", "growth", "profitability"))


@pytest.mark.parametrize(("total", "signal"), [(-2, "SELL"), (-1, "HOLD"), (0, "HOLD"), (1, "HOLD"), (2, "BUY")])
def test_signal_mapping(total, signal):
    assert signal_for(total) == signal


def test_total_plus_two_is_buy():
    target = quote("T", pe_fwd=20.0, revenue_growth=0.20, net_margin=0.10)  # valuation +1, growth +1
    card = build_scorecard(target, make_table(target, PEERS), [])
    assert [f.score for f in card.factors] == [1, 1, 0, 0, 0] and card.preliminary_signal == "BUY"


def test_scorecard_is_deterministic(data):
    table = table_for(data, "COST", ["WMT", "TGT", "BJ", "DG"])
    target = data.market.quote("COST").value
    history = data.market.history("COST").value
    assert build_scorecard(target, table, history.prices) == build_scorecard(target, table, history.prices)


def test_narrower_valuation_band_from_config():
    target = quote("T", pe_fwd=30.0 * 0.88)  # 12% below the median
    table = make_table(target, PEERS)
    assert factor(build_scorecard(target, table, []), "valuation").score == 0
    assert factor(build_scorecard(target, table, [], ScoringConfig(valuation_band=0.10)), "valuation").score == 1
