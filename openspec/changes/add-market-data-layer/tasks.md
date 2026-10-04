# Tasks

## 1. Data contracts and cache

- [x] 1.1 Define Pydantic models `Snapshot`, `Multiples`, `YearValue`, `PricePoint`, `FinancialProfile`, `FilingRef`, `RiskHeadings`, `SearchResult`, `NewsItem` and a `Unavailable` result type in `models.py`; verify with `uv run pyright`
- [x] 1.2 Implement the SQLite cache (`cache.py`) with TTL, no-expiry entries, refresh bypass, hit reporting and corrupt-entry recovery; verify with pytest tests for fresh hit, expiry, persistence across a new connection, bypass and a corrupt row

## 2. Market data

- [x] 2.1 Implement ticker normalisation and validation (pattern, upper-casing, dot-to-hyphen); verify with table-driven tests for `" aapl "`, `brk.b`, `$$$` and the empty string
- [x] 2.2 Implement snapshot, valuation inputs, annual history and daily price history (1 year) with missing-field handling and the equity check; verify with fixture-based tests (AAPL fields present, JPM EV/EBITDA missing, `ZZZZQX` → not found, ETF → not supported)
- [x] 2.3 Implement the concurrent peer batch with per-peer failure reporting; verify with a test where one of three peers fails and the other two return data
- [x] 2.4 Wire all market functions through the cache with the lifetimes from the spec; verify that a second call within the TTL makes no provider call (mock call count)

## 3. SEC risk factors

- [x] 3.1 Implement the fast latest-annual-filing lookup (10-K or 20-F) with the identity set at startup; verify with a live opt-in test that JPM's lookup step takes under 5 s
- [x] 3.2 Implement risk-heading extraction with footer and title filtering, ordering, token cap and truncation flag; verify with fixture tests (AAPL 20–80 headings, no footer lines; an oversized input is truncated and flagged)
- [x] 3.3 Return `Unavailable` for missing filings or empty risk sections, and cache headings by accession number with no expiry; verify with tests for both paths
- [x] 3.4 Run the parse in a single-worker process pool with `start_parser()` (warm-up import) and `stop_parser()`, an inline fallback when no pool is started, and `Unavailable` plus a pool restart on a broken pool; verify with tests that a parse runs in a different PID, that a killed worker yields `Unavailable` and the next parse succeeds, and that an event-loop heartbeat keeps ticking at least every 100 ms during a 2 s CPU-bound fake parse
- [x] 3.5 Keep provider imports at module level in the data modules; verify with a test that importing `equity_agent.data` puts `yfinance`, `edgar` and `tavily` in `sys.modules`

## 4. Web search

- [x] 4.1 Implement competitor search and 30-day news search (basic depth, at most 5 results, snippet ≤ 600 chars); verify with tests on recorded responses
- [x] 4.2 Map missing key, quota exhaustion and service errors to empty results with reasons, never including the key; verify with tests that raise each error type from a fake client
- [x] 4.3 Cache search results for 7 days; verify that a repeated query makes no client call

## 5. Fixtures and checks

- [x] 5.1 Write `scripts/record_fixtures.py` and record fixtures for AAPL, NVDA, JPM, COST and TSLA; verify the fixture folders exist and the offline tests use them
- [x] 5.2 Add a manual demo command `uv run python -m equity_agent.data.inspect AAPL` that prints the snapshot, multiples, filing reference, heading count, search results and timings; verify it runs for all five tickers
- [x] 5.3 Run `uv run pytest` (offline) and `uv run pyright`; verify both pass with no network access
