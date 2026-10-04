# Design

## Context

The measured behaviour of yfinance, edgartools and Tavily is in IMPLEMENTATION_PLAN.md §2.1 and §2.3. The cache
layout is in §4.6. The libraries are synchronous, but the pipeline (next changes) is async.

## Goals / Non-Goals

**Goals:**
- Keep every library call behind a small module with typed Pydantic return values, so later stages and tests never
  touch raw provider dicts.
- Record deterministic fixtures for five tickers, so every later change can be tested offline.

**Non-Goals:**
- Comps math, scoring and LLM calls (later changes).
- Intraday or real-time prices.

## Decisions

- **Sync functions, wrapped with `asyncio.to_thread` by callers.** The libraries are blocking, and keeping the data
  layer sync makes it easy to test. Considered: an async HTTP rewrite, rejected because it would reimplement yfinance.
- **Peer batch uses `concurrent.futures.ThreadPoolExecutor(max_workers=5)`**: 2.0 s vs 3.3 s sequential, measured.
- **yfinance session:** rely on yfinance's own `curl_cffi` session. The smoke check from the foundation change
  verifies the import.
- **Ticker validity = `quoteType == "EQUITY"` and `currentPrice` present.** An unknown symbol returns
  `{'trailingPegRatio': None}` instead of raising.
- **SEC lookup:** `Company(t).get_filings(form=["10-K", "20-F"], trigger_full_load=False).latest()`. This took
  0.08 s vs 27 s for JPM. `set_identity(settings.edgar_identity)` is called once at startup.
- **Heading extraction heuristic:** split the `risk_factors` text into lines and keep lines of 25–260 characters.
  Drop lines matching footer patterns (`| Form 10-K |`, page numbers) and "Item 1A" titles. Keep the original
  order. Cap at about 2,000 tokens, estimated as characters / 4. A known limitation is documented in Risks.
- **Risk extraction runs off the request path when possible.** The result is cached by accession number forever.
  The 17 s JPM parse is paid only on the first run and is pre-warmed for demo tickers (demo-readiness change).
- **Provider libraries are imported at module level** in `data/market.py`, `data/sec.py` and `data/search.py`,
  never inside functions.
  - Measured warm import times: edgartools 7.0 s, of which about 5.5 s is pandas via `edgar._filings`; yfinance
    5.9 s; anthropic 4.1 s; about 10.5 s together.
  - An import inside a function would add that time to the first report.
  - `smoke.py` keeps its imports inside functions on purpose, so that one failing library doesn't stop the other
    checks.
- **Filing parsing runs in a `ProcessPoolExecutor(max_workers=1)`, not in a thread.**
  - Parsing is CPU-bound Python. In a thread it holds the GIL and slows the event loop and every other branch for up
    to 17 s.
  - On Windows a new process re-imports edgartools (about 7 s). So `data/sec.py` exposes `start_parser()` and
    `stop_parser()`, the API calls them from its lifespan (`add-research-api`), and `start_parser()` submits a warm-up
    job that imports `edgar` in the worker.
  - Only the parse (`filing.obj().risk_factors` plus heading extraction) runs in the worker. The filing lookup is
    I/O-bound and stays on a thread.
  - The worker function is a top-level function that takes the accession number and the identity. It sets the
    identity in the worker, because the parent's `set_identity` doesn't carry over to a spawned process. It returns
    plain headings.
  - A `BrokenProcessPool` is mapped to `Unavailable` and the pool is restarted.
  - Without a started pool, for example in the CLI or tests, parsing runs inline. This keeps sync callers simple.
  - Considered: `asyncio.to_thread` only. Rejected because of the GIL contention described above.
- **Cache = SQLite table `(key TEXT PRIMARY KEY, value TEXT, expires_at REAL NULL)`** storing JSON-serialised
  Pydantic models. A `@cached(kind, ttl)` decorator returns `(value, hit: bool)`. Considered: `diskcache`, rejected
  as an extra dependency for a small amount of code. The edgartools HTTP cache is pointed at `backend/.cache/edgar`.
- **Fixtures:** a `record_fixtures.py` script serialises the module outputs (Pydantic JSON) for the five tickers into
  `tests/fixtures/<T>/`. Tests patch the provider calls to load them. The script runs manually, never in pytest.

## Risks / Trade-offs

- [The heading heuristic may keep some body sentences or miss bold-only headings in some filings] → Fixture tests
  check AAPL, NVDA, JPM and COST counts. The Risk Agent (later) ranks and condenses headings, so some noise is
  tolerated.
- [Yahoo field names change] → Every field is read with `.get()` into `Optional` fields; tests cover missing fields.
- [The worker process adds about 7 s and a second Python process's memory to service start-up] → It is paid once at start, not per request.
  The `dev:all` reload pays it again; `start:all` (foundation change) doesn't reload.
- [Fixtures go stale as prices move] → Tests assert on structure and invariants, not exact prices.
