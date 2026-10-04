# Design

## Context

The redundancy review's findings and their evidence are in proposal.md. These measurements, taken on 2026-10-03
before any change, are the baseline the tasks are checked against:

| Measure | Baseline | Target |
|---|---|---|
| `except` blocks in `pipeline.py` | 15 | ≤ 6 |
| hand-written cache-hit records in `pipeline.py` | 8 | 0 (one helper) |
| hand-written usage records in `pipeline.py` | 10 | ≤ 2 |
| message parsing `str(error).split(":")` | 2 | 0 |
| hand-rolled ticker cleaning (`.strip().upper()` on tickers) | 4 | 0 |
| metric formatters | 3 (`scoring.fmt`, `payloads.metric`, word truncation ×2) | 1 module |
| copies of "run a report, get the result" | 3 + 1 comps assembly | 1 + 1 |
| `pipeline.py` / `cli.py` / `smoke.py` lines | 489 / 82 / 110 | about 400 / 50 / 80 |

**Outcome (2026-10-03):** every structural target was met (6 / 1 / 1 / 0 / 0 / one module / one runner). The
line-count estimates were not: 492 / 72 / 106. `pipeline.py` absorbed the shared runner, `RunFailed` and the
cache-clearing helper that the CLI and the evaluation used to duplicate, and `smoke.py` now drives the full gateway
path (warm-up plus a streamed call) instead of one bare API call. The backend source as a whole went from about
3,650 to 3,522 lines, including the two new modules.

The offline suite (184 tests, FakeClaude, recorded fixtures) and pyright are the safety net. They test behaviour
well but don't pin the exact text agents receive, so a characterisation test is added first (decision 1).

## Goals / Non-Goals

**Goals:**
- Each behaviour written once, with one name, so the API change (`add-research-api`) builds on single entry points.
- Behaviour preserved, as proven by the characterisation test. The only intended output change is debt-to-equity
  text in the printed comps table, now "0.78" everywhere.
- Measurable progress toward the targets above.

**Non-Goals:**
- Changing prompts, models, scoring thresholds, cache lifetimes, the report schema or any spec'd behaviour beyond the
  six added requirements.
- Merging the three manual commands (`research`, `data.inspect`, `scoring`) into one. They answer different
  questions (full report, data layer only, comps math only). Only their shared parts are de-duplicated.
- Performance work. Timings are re-measured once only to confirm there is no regression.

## Decisions

### 1. Characterisation test before any refactor

`tests/test_characterisation.py` runs the pipeline offline for the five fixture tickers with FakeClaude and a
fixed clock. It stores, per ticker, under `tests/golden/<T>.json`:

- the report with volatile fields removed (`generated_at`, `timings_ms`, `llm_usage[].ms`);
- every user message sent to each agent (agent name and exact text).

The test compares a fresh run with the golden files, with an opt-in `UPDATE_GOLDEN=1` to rewrite them. The golden
files are recorded on the current code (task 1.1) and must stay unchanged through every task group. The one planned
exception is decision 5's debt-to-equity text, if any agent input contains it, recorded as a reviewed golden
update.

- Considered: relying on the existing behavioural tests only. Rejected: they wouldn't notice an agent input
  changing from "0.78" to "0.8", or a reordered payload key, both of which change model behaviour.

### 2. One failure vocabulary

| Situation | Type after the change | Replaces |
|---|---|---|
| A data request that cannot be served (bad, unknown or unsupported ticker; provider failure) | `DataError` exception with `.reason` (fixed text) and `.ticker` | message parsing with `split(":")` |
| An expected absence that is not an error (no filing, no risk section, search not possible) | `Unavailable(reason)` value | `SearchOutcome.reason`, `Unavailable` (kept) |
| An agent stage that failed (model error, refusal, timeout, invalid output after the re-ask) | `StageFailed` exception with `.kind` and `.usages` | `StageFailed` plus `LlmError` reaching the pipeline |
| A failed section in the report | `StageError(stage, message)` model | unchanged |

- **`DataError`.** Subclasses set a class-level `reason` ("invalid ticker", "ticker not found", "only individual
  stocks are supported"). `ProviderError(DataError)` with reason "provider error" replaces the ad-hoc
  `f"provider error ({type(error).__name__})"` strings. `str(error)` stays a full sentence for logs.
- **Search.** `SearchData.competitors()` and `.news()` return `Fetched[SearchResults[T] | Unavailable]`.
  `SearchResults[T]` is the items-only successor of `SearchOutcome`. A missing key, exhausted quota or service
  error becomes `Unavailable("quota exhausted")` and so on. The web-search spec's "empty result with a reason" is
  met by the shared shape, and callers branch once with `isinstance`.
- **`LlmError` stays inside the gateway.** `ClaudeAgent.run()` already converts it to `StageFailed`. The Writer's
  streaming path is the one place where it still reaches the pipeline; a small `WriterAgent.stream()` wrapper does
  the same conversion, so the pipeline catches only `StageFailed`.
- Considered: one `Result[T]` type for everything. Rejected: exceptions for "stop this request" and values for
  "absent but fine" are both clearer at their call sites than a universal result type, and the table above is the
  whole vocabulary.

### 3. One cache-hit convention

- `Fetched[T]` changes from `(value, key, hit)` to `(value, hits: list[str])`, with a `hit` property for
  `bool(hits)`.
- `Cache.fetch()` returns `hits=[key]` on a hit. `MarketData.peers()` and `SecData.risk_headings()` return
  `Fetched` too, merging the keys of their inner lookups. This removes the two `(value, hits)` tuple returns.
- The pipeline records hits through one helper, `self.use(fetched) -> value`, which appends `fetched.hits`. The
  peer-choice and risk-selection agent caches go through `Cache.fetch` as well (with `store=` vetoes where needed),
  so they report hits the same way.

### 4. Pipeline plumbing in one place

- **`_Run.stage(name, work, *, degrade=None)`.** With `degrade` set to a failure-message prefix, it catches
  `StageFailed` (recording its usages), `DataError` and any other exception (logged with the traceback). It emits
  the error event and the failed stage event, and returns a `StageError` instead of raising. Without `degrade` it
  re-raises, as now (the validation stage).
- **`_Run.agent(agent, data) -> output`.** It runs a `ClaudeAgent`, records `run.usages` (or the failure's usages)
  and returns the output, so no branch touches `self.usage` directly. The Writer's `stream()` reports usage
  through the same list.
- **Branches keep only their own logic:** the comps re-ask and fallback, the risk-selection cache, and the analyst's
  preliminary-signal fallback.
- Considered: decorators per branch. Rejected: the helper is more explicit and keeps each branch readable top to
  bottom.

### 5. One formatting module

`equity_agent/formatting.py` holds `METRIC_LABELS`, `PERCENT_METRICS`, `metric_text(name, value)`, `money(value,
currency)`, `pct_change(value)` and `truncate_words(text, limit)`. All of these move here from `scoring.py`,
`agents/payloads.py`, `data/market.py` and `data/search.py`.

- Debt-to-equity uses two decimals everywhere, matching what agents already receive. The printed comps table changes
  from "0.8" to "0.78".
- Scorecard explanation strings don't use debt-to-equity, so their text is unchanged, as the characterisation test
  will show.
- `run_ragas._fmt` (scores to three decimals) is a different domain and stays.

### 6. One ticker normaliser

`normalize_ticker()` (validation, upper case, dot to hyphen) is used for model-proposed peers in the pipeline, in
`CompsAgent.validate` (an `InvalidTicker` becomes the rule violation) and for the explain call's tickers. The
duplicated pattern check in `CompsAgent.validate` goes away.

### 7. One report runner and shared comps assembly

- **`pipeline.run_report(services, ticker, *, refresh=False, on_event=None) -> ResearchReport`.** It consumes
  `Pipeline.run()`, forwards events to `on_event`, raises `RunFailed(stage, reason)` on a terminal error and
  returns the report. Its users are `cli.run()`, `eval/run_ragas.generate_report()` and a `conftest.py` fixture.
  The API change will stream from `Pipeline.run()` directly but reuse `RunFailed` for its terminal-error mapping.
- **`scoring.assemble_comps(target_quote, tickers, batch, *, rationales, origin, sources, config) -> CompsTable`.**
  It applies eligibility to an already-fetched peer batch and builds the table. It takes the batch rather than the
  market client, so `scoring.py` stays free of network calls. The pipeline's cached, agent and fallback paths
  (through one `comps_table()` helper that fetches the batch) and the `scoring` demo all call it.
- **Agents report usage as it happens.** `ClaudeAgent.run(llm, data, on_usage)` calls `on_usage` per model call,
  as the Writer's stream already did, so the pipeline records usage through one callback.
- **Agent caches through the cache's own fetch.** `Cache.lookup()` (a read that reports its hit) and
  `Cache.afetch()` (fetch with an async loader) let the peer choice and the risk selection report hits like every
  other lookup.
- **`scoring.scorecard_lines(card) -> list[str]`** is shared by the CLI report and the scoring demo.

### 8. Field lists with one source

- **`market.QUOTE_FIELDS`.** `parse_quote` reads the provider dictionary only through a guarded accessor that raises
  for an undeclared field. `scripts/record_fixtures.py` imports `QUOTE_FIELDS` instead of keeping `INFO_KEYS`. A test
  parses every fixture, which fails on any undeclared read.
- **`PeerChoice`** moves to `models.py` with `PeerChoice.from_table(table)` and
  `PeerChoice.table_kwargs() -> dict` (rationales, origin, sources). The four fields are listed once.
- **`Services.models: Mapping[AgentName, AgentConfig]`** replaces `model_names`. `live_services()` passes
  `settings.agents`; tests default to `config.DEFAULT_MODELS` with effort `low`. The `"default"` fallback string is
  removed, so cache keys always name a real model.

### 9. Smoke check through production paths

Each check keeps its import inside the function, so one broken library doesn't stop the others:

- **SEC:** `sec.configure()`, then `EdgarSource(identity).latest_annual("AAPL")`.
- **Yahoo:** `parse_quote("AAPL", YahooSource().info("AAPL"))`.
- **Tavily:** `TavilySource(key).search(..., topic="general", days=None)`.
- **Claude:** `Gateway(settings).warm()` (every model exists), then one short `Gateway.stream("writer", ...)`.

The `curl_cffi` check is unchanged. The checks stay sequential; their speed doesn't matter.

### 10. Test infrastructure

- **`tests/fakes.py`** gains `fake_services(llm, data=None)`, `collect_events(...)` and
  `make_report(...)` (backed by `run_report`). It is an ordinary module that tests already import; pytest discourages
  importing from `conftest.py`. The duplicated `services()`, `collect()`, `report_for()` and
  `run(coro)` helpers are removed from the test modules.
- **`FakeClaude.parse`** dispatches on `output_model` (`PeerPicks`, `PeerRationales`, `RiskSelection`,
  `AnalystOutput`), not on the shape of the input.
- **`FixtureSearchSource`** builds its company-name → ticker index once, at construction.

### 11. Evaluation snapshots

- The snapshot and comparison logic lives in `equity_agent/evaluation/runs.py`, so it is tested offline without
  the `eval` group; `eval/run_ragas.py` and `eval/compare.py` are thin command lines over it.
- `eval/run_ragas.py --snapshot NAME` copies `ragas_scores.json` and `ragas_summary.md` to `eval/runs/NAME/`.
  `eval/reports/` keeps only the latest run's reports, for `--reuse`.
- The three existing folders migrate to `eval/runs/2026-10-03-baseline/`, `…-prompt-fixes/` and
  `…-two-call-comps/`, with scores and summaries only. Their `reports/` copies are deleted.
- The baseline note (`docs/2026-10-03-ragas-baseline.md`) is updated to point at the new paths.

### 12. Documentation with one source of truth

- IMPLEMENTATION_PLAN.md §5 is replaced by a short summary and a pointer to `backend/src/equity_agent/models.py`
  as the source of truth, and the stale statements are corrected (daily prices, pick and explain calls).
- The README keeps the latest evaluation table and links to the dated notes for the history.

### Order of work

1. Characterisation test (decision 1).
2. Formatting (5) and ticker normalisation (6): leaf modules, lowest risk.
3. Failure vocabulary (2), then the cache-hit convention (3). Both touch the data layer, before the pipeline is
   restructured.
4. Pipeline plumbing (4), then the report runner and comps assembly (7).
5. Field lists (8), smoke check (9) and test infrastructure (10).
6. Evaluation snapshots (11) and documentation (12).

Each group ends with the full offline suite, pyright and the characterisation test green.

## Risks / Trade-offs

- **[A refactor changes agent inputs unnoticed, and model behaviour with them]** → The characterisation test pins
  every agent input byte for byte for five tickers. Any intended change is a reviewed golden update listed in the
  task.
- **[`Fetched` changes shape across the data layer and its tests]** → Done in one task group together with its
  callers. pyright catches every missed call site.
- **[`degrade` hides real bugs inside a branch]** → It logs the full traceback, the error event names the
  exception type, and branch-level tests still assert the degraded content. The validation stage never degrades.
- **[Deleting the snapshot reports loses inspectable outputs]** → The scores, summaries and the dated note keep the
  results, and the latest reports stay in `eval/reports/`. Nothing is committed yet, so the deletion is permanent:
  the task asks for confirmation before deleting. If the reports are wanted, it can be skipped without affecting
  the rest.
- **[A larger diff right before the API milestone]** → Measurable targets, task-by-task verification, and no
  behaviour change beyond the six added requirements keep the diff reviewable.
