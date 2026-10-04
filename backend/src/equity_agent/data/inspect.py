"""Manual check of the data layer: `uv run python -m equity_agent.data.inspect AAPL [--offline] [--refresh]`.

Live mode uses the real providers and the persistent cache (up to 2 Tavily credits per uncached ticker).
"""

from __future__ import annotations

import argparse
import sys
import time

from equity_agent.config import load_settings
from equity_agent.data import DataError, DataLayer, normalize_ticker
from equity_agent.models import Unavailable


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tickers", nargs="+")
    parser.add_argument("--offline", action="store_true", help="read recorded fixtures instead of live providers")
    parser.add_argument("--refresh", action="store_true", help="bypass cached quotes, history and searches")
    args = parser.parse_args(argv)
    data = DataLayer.recorded() if args.offline else DataLayer.live(load_settings())
    try:
        for raw in args.tickers:
            start = time.perf_counter()
            try:
                ticker = normalize_ticker(raw)
                quote = data.market.quote(ticker, refresh=args.refresh)
            except DataError as error:
                print(f"{raw}: {error}\n")
                continue
            snap, mult = quote.value.snapshot, quote.value.multiples
            print(f"{ticker}  {snap.name}  {snap.sector} / {snap.industry}  {snap.currency} {snap.price:,.2f}")
            print(f"  market cap {snap.market_cap or 0:,.0f}  52w {snap.week52_low}-{snap.week52_high}")
            print(f"  multiples {mult.model_dump(exclude_none=True)}")
            history = data.market.history(ticker, refresh=args.refresh).value
            print(f"  revenue {[(y.year, round(y.value / 1e9, 1)) for y in history.revenue]} (bn); {len(history.prices)} daily closes")
            risks = data.sec.risk_headings(ticker).value
            if isinstance(risks, Unavailable):
                print(f"  risk headings unavailable: {risks.reason}")
            else:
                print(f"  {risks.filing.form} {risks.filing.filing_date}: {len(risks.headings)} headings, truncated={risks.truncated}")
            for label, found in (("competitor", data.search.competitors(snap.name, snap.industry).value),
                                 ("news", data.search.news(snap.name).value)):
                if isinstance(found, Unavailable):
                    print(f"  {label} search unavailable: {found.reason}")
                else:
                    print(f"  {label} search: {len(found.items)} results")
            print(f"  {time.perf_counter() - start:.1f}s\n")
    finally:
        data.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
