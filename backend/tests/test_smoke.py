"""The smoke check must fail when the production call it wraps fails (offline: every call is patched)."""

import pytest

from equity_agent import smoke
from equity_agent.config import load_settings
from equity_agent.data.market import YahooSource
from equity_agent.data.search import TavilySource
from equity_agent.data.sec import EdgarSource
from equity_agent.llm import Gateway

SETTINGS = load_settings({"ANTHROPIC_API_KEY": "sk-test", "TAVILY_API_KEY": "t", "EDGAR_IDENTITY": "A a@b.c"})


def boom(*args, **kwargs):
    raise ConnectionError("down")


async def aboom(*args, **kwargs):
    raise ConnectionError("down")


@pytest.mark.parametrize(
    ("check", "target", "name", "replacement"),
    [
        (smoke.check_sec, EdgarSource, "latest_annual", lambda self, ticker: None),
        (smoke.check_yahoo, YahooSource, "info", lambda self, ticker: {"trailingPegRatio": None}),
        (smoke.check_tavily, TavilySource, "search", boom),
        (smoke.check_claude, Gateway, "warm", aboom),
    ],
)
def test_check_fails_when_production_call_fails(monkeypatch, check, target, name, replacement):
    monkeypatch.setattr("equity_agent.data.sec.configure", lambda identity: None)
    monkeypatch.setattr(target, name, replacement)
    with pytest.raises(Exception):  # noqa: B017 - any failure counts; main() reports it as FAIL
        check(SETTINGS)


def test_checks_use_production_code_paths():
    import inspect

    source = inspect.getsource(smoke)
    for production in ("EdgarSource", "parse_quote", "TavilySource", "Gateway"):
        assert production in source
    assert "get_filings" not in source and "messages.create" not in source
