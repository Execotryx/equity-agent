"""Manual smoke check of every external dependency: `uv run python -m equity_agent.smoke`.

Spends a fraction of a cent of Anthropic credit and 1 Tavily credit. Never run it from pytest.
Exit code 0 when every check passes, 1 otherwise.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable

from equity_agent.config import ConfigError, Settings, load_settings

Check = tuple[str, Callable[[Settings], str]]


def check_curl_cffi(settings: Settings) -> str:
    # yfinance silently falls back to plain requests (and gets rate-limited) when this import fails,
    # e.g. when the project sits in a path too deep for Windows MAX_PATH.
    from curl_cffi import requests  # noqa: F401

    return "curl_cffi imports (yfinance can impersonate a browser)"


def check_claude(settings: Settings) -> str:
    import asyncio

    from equity_agent.llm import Gateway
    from equity_agent.models import LlmUsage

    usages: list[LlmUsage] = []

    async def go() -> str:
        gateway = Gateway(settings)  # the service's own client, request settings and refusal fallback
        try:
            await gateway.warm()  # free; fails on a misspelled model setting
            parts = [t async for t in gateway.stream("writer", "Reply with the single word OK.", "Say OK.", usages.append)]
            return "".join(parts).strip()
        finally:
            await gateway.close()

    text = asyncio.run(go())
    models = sorted({cfg.model for cfg in settings.agents.values()})
    return f"models exist: {', '.join(models)}; {usages[-1].model} replied {text[:20]!r}"


def check_tavily(settings: Settings) -> str:
    from equity_agent.data.search import TavilySource

    results = TavilySource(settings.tavily_api_key).search("Apple Inc competitors", topic="general", days=None)
    count = len(results.get("results", []))
    if count == 0:
        raise RuntimeError("search returned no results")
    return f"basic search returned {count} results (1 credit)"


def check_sec(settings: Settings) -> str:
    from equity_agent.data import sec

    sec.configure(settings.edgar_identity)
    ref = sec.EdgarSource(settings.edgar_identity).latest_annual("AAPL")  # the service's lookup, amendments excluded
    if ref is None:
        raise RuntimeError("no 10-K found for AAPL")
    return f"AAPL latest {ref.form} filed {ref.filing_date} ({ref.accession_no})"


def check_yahoo(settings: Settings) -> str:
    from equity_agent.data.market import YahooSource, parse_quote

    quote = parse_quote("AAPL", YahooSource().info("AAPL"))  # the service's validation: an equity with a price
    return f"AAPL price {quote.snapshot.price}"


CHECKS: list[Check] = [
    ("curl_cffi", check_curl_cffi),
    ("Claude", check_claude),
    ("Tavily", check_tavily),
    ("SEC EDGAR", check_sec),
    ("Yahoo Finance", check_yahoo),
]


def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as error:
        print(f"FAIL  configuration: {error}")
        return 1

    failures = 0
    for name, check in CHECKS:
        start = time.perf_counter()
        try:
            detail = check(settings)
            status = "PASS"
        except Exception as error:  # noqa: BLE001 - report every failure, keep checking the rest
            failures += 1
            status, detail = "FAIL", settings.redact(f"{type(error).__name__}: {error}")
        print(f"{status}  {name:<14} {time.perf_counter() - start:5.1f}s  {detail}")
    print(f"\n{len(CHECKS) - failures}/{len(CHECKS)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
