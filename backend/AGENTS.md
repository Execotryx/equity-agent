# Backend guide

Read the root guide for shared contracts and change-record rules. Paths below are relative to `src/equity_agent/`.

## Architecture

- `models.py`: shared Pydantic contracts; missing values are `None`, percentages are fractions.
- `data/`: Yahoo, KASE, SEC EDGAR and Tavily adapters. `cache.py` owns SQLite persistence and TTLs.
- `scoring.py`: deterministic arithmetic, peer eligibility and signal scoring. Models never calculate financial figures.
- `agents/`: compact evidence payloads, Markdown prompts, output validation and one bounded re-ask.
- `pipeline.py`: shared CLI, evaluation and API execution, concurrent branches and degradation.
- `streaming.py`: independently pumped report runs replayed to SSE subscribers.

Read [data/AGENTS.md](src/equity_agent/data/AGENTS.md) when changing provider integrations, valuation inputs,
cache behavior or recording. Read [agents/AGENTS.md](src/equity_agent/agents/AGENTS.md) when changing prompts,
payloads or generated/cached output validation. Test-specific rules live in [tests/AGENTS.md](tests/AGENTS.md).

## Execution invariants

- Normalize tickers before cache access. Serve unexpired reports without provider calls; Refresh bypasses report reuse.
- Evaluate every fallback peer candidate. Worker concurrency and the displayed eligible-peer limit are separate.
  Recheck cached choices against current eligibility and replace choices without enough valid peers.
  Exclude mapped aliases of the target from its peers.
- Validate generated and cached risk selections against their source headings using the agent guide's full contract.
- Missing momentum evidence remains neutral and visible. Preserve provider and enrichment diagnostics.
- A subscriber disconnect stops that subscription; the registry pump continues to cache its report.
  Shutdown stops accepting runs and cancels model work once. Drain owned tasks, background explanations and
  already-running provider threads before closing shared services. Cancellation cannot interrupt a running Python
  provider thread. Terminal SSE events close subscriptions.

## Verification

From `backend/`, run `uv run pytest` and `uv run pyright`. On Windows, the existing environment also supports
`.venv/Scripts/python.exe -m pytest` and `.venv/Scripts/pyright.exe`.
Always run Pyright after Python changes; if unavailable, try `uv add pyright`.
Review fixture/golden differences intentionally and keep live tests separate from offline gates.
