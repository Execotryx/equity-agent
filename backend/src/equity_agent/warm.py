"""Pre-warm the caches before a demo: `uv run python -m equity_agent.warm AAPL NVDA JPM COST TSLA`.

For each ticker it fetches the quote, history, filing risk headings, searches and peers, and runs the Comps and Risk
agents, so a following report only calls the Analyst and Writer. One failing ticker doesn't stop the others.
"""

from __future__ import annotations

import asyncio
import sys

from equity_agent.config import load_settings
from equity_agent.formatting import MISSING
from equity_agent.pipeline import Services, WarmResult, live_services, warm_ticker

DEMO_TICKERS = ["AAPL", "NVDA", "JPM", "COST", "TSLA"]


async def warm_all(services: Services, tickers: list[str]) -> list[WarmResult]:
    results: list[WarmResult] = []
    for ticker in tickers:
        result = await warm_ticker(services, ticker)
        print(f"{result.ticker:<7} {result.status:<9} {result.ms / 1000:5.1f} s  {'; '.join(result.problems) or MISSING}")
        results.append(result)
    return results


async def main(tickers: list[str]) -> int:
    services = live_services(load_settings())
    services.data.sec.start_parser()  # parse filings in the worker, as the API does
    try:
        results = await warm_all(services, tickers)
    finally:
        services.data.close()
        await services.llm.close()
    return 0 if all(r.status == "ok" for r in results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:] or DEMO_TICKERS)))
