"""Record provider data for offline tests: `uv run python scripts/record_fixtures.py [TICKERS...]`.

Spends 2 Tavily credits per target ticker. Never run from pytest. Peer tickers get only `info.json`.
"""

from __future__ import annotations

import sys
from typing import Any

from equity_agent.config import load_settings
from equity_agent.data import market, search, sec
from equity_agent.data.kase import sec_ticker
from equity_agent.data.fixtures import FIXTURES_DIR
from equity_agent.demo import quote_subset, search_file, trimmed_search, write_fixture

TARGETS = ["AAPL", "NVDA", "JPM", "COST", "TSLA"]
PEERS = {
    "AAPL": ["MSFT", "GOOGL", "DELL", "HPQ", "SONY"],
    "NVDA": ["AMD", "INTC", "AVGO", "QCOM", "TSM"],
    "JPM": ["BAC", "C", "WFC", "GS", "MS"],
    "COST": ["WMT", "TGT", "BJ", "DG", "KR"],
    "TSLA": ["GM", "F", "TM", "RIVN", "LCID"],
}


def write(ticker: str, name: str, data: Any) -> None:
    path = write_fixture(FIXTURES_DIR, ticker, name, data)
    print(f"  wrote {path.relative_to(FIXTURES_DIR.parent.parent)}")


def record_info(source: market.MarketSource, ticker: str) -> dict[str, Any]:
    subset = quote_subset(source.info(ticker))
    write(ticker, "info.json", subset)
    return subset


def main(targets: list[str]) -> int:
    settings = load_settings()
    sec.configure(settings.edgar_identity)
    yahoo = market.live_source()
    edgar_source = sec.EdgarSource(settings.edgar_identity)
    tavily = search.TavilySource(settings.tavily_api_key)
    for ticker in targets:
        print(ticker)
        info = record_info(yahoo, ticker)
        write(ticker, "income.json", yahoo.income(ticker))
        write(ticker, "closes.json", yahoo.closes(ticker))
        filing_ticker = sec_ticker(ticker)
        ref = edgar_source.latest_annual(filing_ticker) if filing_ticker else None
        if ref is not None:
            write(ref.ticker, "filing.json", ref.model_dump(mode="json"))
            write(ref.ticker, "risk_text.txt", edgar_source.risk_text(ref) or "")
        name = info.get("longName", ticker)
        query = f"{name} main competitors {info.get('industry', '')}".strip()
        write(ticker, search_file("general"), trimmed_search(tavily.search(query, topic="general", days=None)))
        news = tavily.search(f"{name} stock news", topic="news", days=search.NEWS_DAYS)
        write(ticker, search_file("news"), trimmed_search(news))
        for peer in PEERS.get(ticker, []):
            record_info(yahoo, peer)
    return 0


if __name__ == "__main__":
    sys.exit(main([market.normalize_ticker(t) for t in sys.argv[1:]] or TARGETS))
