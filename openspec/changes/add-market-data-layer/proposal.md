# Proposal

## Why

Every part of the report (financials, comps, risks, signal) depends on fast and reliable data about a ticker. The
planning benchmarks (IMPLEMENTATION_PLAN.md §2.1) found four problems with the raw libraries:

- Unknown tickers don't raise an error.
- Banks have no EBITDA.
- A naive SEC lookup takes 27 s for JPM.
- Raw 10-K risk text is 10k–28k tokens.

This change builds a data layer that handles all four. It contains no LLM calls, and it caches results so repeated
runs are fast. This is milestone M1.

## What Changes

- Ticker normalisation and validation against live market data.
- A company snapshot (price, market cap, sector, industry, 52-week range, business summary), valuation inputs
  (multiples, margins, growth, analyst target), 4 years of annual income data, and 1 year of daily closing prices.
- A batch fetch of several peer tickers in parallel.
- A fast lookup of the latest annual SEC filing (10-K, or 20-F for foreign issuers), extraction of a compact list
  of risk-factor headings, and a clear "unavailable" result when no filing exists.
- Filing parsing in a warm, reusable worker process, so a long parse never stalls the service. Provider libraries
  load once, up front, instead of on the first request.
- Web search for competitor discovery and recent news, with result limits and graceful quota failure.
- A persistent local cache with a time-to-live per data type and a way to bypass it.
- Recorded fixtures for AAPL, NVDA, JPM, COST and TSLA so later changes can test offline.

## Capabilities

### New Capabilities

- `market-data`: ticker validation, company snapshot, valuation inputs, financial history, price history, batch peer fetch.
- `sec-risk-factors`: latest annual filing lookup and compact risk-factor heading extraction.
- `web-search`: competitor and news search with bounded results and quota handling.
- `data-cache`: persistent time-bounded caching of fetched data, with bypass and observability of cache hits.

### Modified Capabilities

(none)

## Impact

- New backend modules: `data/market.py`, `data/sec.py`, `data/search.py`, `cache.py`, `models.py` (data contracts).
- New SQLite file `backend/.cache/research.db` and the edgartools cache directory.
- Tavily credits are used: at most 2 basic searches per report, and none when cached.
- Depends on `setup-project-foundation`.
