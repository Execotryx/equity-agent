import pytest

from equity_agent.formatting import metric_text, money, pct_change, truncate_words


@pytest.mark.parametrize(
    ("metric", "value", "text"),
    [
        ("debt_to_equity", 0.78445, "0.78"),
        ("net_margin", 0.27619, "27.6%"),
        ("dividend_yield", 0.0033, "0.3%"),
        ("pe_fwd", 34.821583, "34.8"),
        ("pe_ttm", -4.0, None),
        ("ev_ebitda", 0.0, None),
        ("net_margin", -0.039, "-3.9%"),
        ("roe", None, None),
    ],
)
def test_metric_text(metric, value, text):
    assert metric_text(metric, value) == text


def test_money_and_change():
    assert money(4_869_931_925_504) == "$4.87T"
    assert money(416_161_000_000) == "$416.16B"
    assert money(-2_500_000, "EUR") == "-EUR 2.50M"
    assert money(None) is None
    assert pct_change(0.594) == "+59%" and pct_change(-0.04) == "-4%" and pct_change(None) is None


def test_truncate_words_at_boundary():
    assert truncate_words("short", 10) == "short"
    text = "Apple designs smartphones and computers"
    cut = truncate_words(text, 20)
    assert cut == "Apple designs…" and len(cut) <= 20
