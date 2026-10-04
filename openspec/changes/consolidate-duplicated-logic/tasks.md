# Tasks

## 1. Safety net

- [x] 1.1 Add `tests/test_characterisation.py` (five fixture tickers, FakeClaude, fixed clock) and record `tests/golden/<T>.json` on the current code, with the report minus volatile fields plus every agent user message; verify it passes twice in a row and fails when one payload key is renamed by hand (then revert)
- [x] 1.2 Record the baseline counts from design.md with a small script `scripts/redundancy_counts.py` (`except` blocks, hit and usage records, `split(":")`, hand-rolled ticker cleaning, lines per module); verify it prints the baseline table

## 2. Formatting and tickers

- [x] 2.1 Create `formatting.py` (`METRIC_LABELS`, `PERCENT_METRICS`, `metric_text`, `money`, `pct_change`, `truncate_words`) and switch `scoring.py`, `agents/payloads.py`, `data/market.py` and `data/search.py` to it, deleting `scoring.fmt`, `payloads.metric`, `payloads.money` and both truncation copies; verify with table-driven tests (debt-to-equity 0.78445 → "0.78", net margin 0.27619 → "27.6%", negative P/E → not meaningful, truncation at a word boundary) and an unchanged characterisation test
- [x] 2.2 Use `normalize_ticker` for model-proposed peers in the pipeline, in `CompsAgent.validate` and for explain-call tickers, removing the duplicated pattern check; verify with tests for `brk.b` from the model → `BRK-B` and an invalid symbol reported as a rule violation, plus an unchanged characterisation test

## 3. Failure vocabulary and cache hits

- [x] 3.1 Give `DataError` a class-level `reason` and a `ticker`, add `ProviderError`, and replace both `str(error).split(":")[0]` uses with `.reason`; verify with tests for target and peer `ZZZZQX` (both "ticker not found") and a test that rewording a message leaves the reasons unchanged
- [x] 3.2 Replace `SearchOutcome` with `SearchResults[T] | Unavailable` in `SearchData` and the pipeline; verify the existing search failure tests (not configured, quota exhausted, service error, never cached, no key in reasons) pass with the new shape
- [x] 3.3 Add `WriterAgent.stream()` converting `LlmError` to `StageFailed`, so the pipeline catches only `StageFailed`; verify the writer failure test still yields a narrative `StageError`
- [x] 3.4 Change `Fetched` to `(value, hits)` and make `MarketData.peers()` and `SecData.risk_headings()` return `Fetched`; verify with a test that a warm peer batch plus a warm filing and headings put all four keys in the report's cache-hit list, and pyright with zero errors

## 4. Pipeline plumbing

- [x] 4.1 Add `_Run.use(fetched)`, `_Run.agent(agent, data)` and the `degrade` mode of `_Run.stage`, then rewrite the five branches with them, routing the agent caches through `Cache.fetch`; verify every degraded-branch test passes, the characterisation test is unchanged, and the counts script reports ≤ 6 `except` blocks, 0 hand-written hit records and ≤ 2 usage records in `pipeline.py`
- [x] 4.2 Add `pipeline.run_report()` and `RunFailed`, and use them in `cli.run()` and `eval/run_ragas.generate_report()`; verify with a test that `ZZZZQX` raises `RunFailed("validate", "ticker not found")` with no model or search calls, and a test that the CLI path and the evaluation path give identical reports on the same fixtures apart from volatile fields
- [x] 4.3 Add `scoring.assemble_comps()` and `scoring.scorecard_lines()` and use them in the pipeline's cached and fallback paths, the `scoring` demo and the CLI; verify the demo output for `AAPL MSFT GOOGL DELL --offline` matches before and after except the debt-to-equity column ("0.78"), and an unchanged characterisation test

## 5. Field lists, smoke check and tests

- [x] 5.1 Declare `market.QUOTE_FIELDS`, read quotes through a guarded accessor, and make `scripts/record_fixtures.py` import it; verify with a test that parses every recorded `info.json`, and a test that an undeclared read raises
- [x] 5.2 Move `PeerChoice` to `models.py` with `from_table()` and `table_kwargs()`, and replace `Services.model_names` with `Services.models` from settings (tests default to `DEFAULT_MODELS`); verify the peer-cache tests, and that cache keys contain the configured model name, never "default"
- [x] 5.3 Rewrite `smoke.py` on `EdgarSource`, `parse_quote`/`YahooSource`, `TavilySource` and `Gateway` (warm plus one short Writer stream), keeping imports inside each check; verify with an offline test that monkeypatches each production call to fail and sees the matching check fail, then run the live smoke check (5/5 PASS, under $0.01)
- [x] 5.4 Move the shared test helpers to `tests/fakes.py` (an importable module; importing from `conftest.py` is discouraged by pytest), make `FakeClaude.parse` dispatch on `output_model`, and index `FixtureSearchSource` once; verify the whole offline suite passes with no duplicated helper definitions (grep for `def services`, `def collect`, `def report_for`, `def run(` outside `fakes.py` returns nothing)

## 6. Evaluation snapshots and documentation

- [x] 6.1 Add `--snapshot NAME` to `eval/run_ragas.py` (scores and summary to `eval/runs/NAME/`), and make `eval/compare.py` accept snapshot names as well as paths; verify with an offline test of the snapshot writer and `compare.py` on two snapshot folders
- [x] 6.2 Migrate the three existing folders to `eval/runs/2026-10-03-{baseline,prompt-fixes,two-call-comps}/` with scores and summaries only, and update the paths in `docs/2026-10-03-ragas-baseline.md` and the README. Ask the user before deleting the copied `reports/` folders. Verify `compare.py 2026-10-03-baseline 2026-10-03-two-call-comps` prints the documented numbers
- [x] 6.3 Replace IMPLEMENTATION_PLAN.md §5 with a summary and a pointer to `models.py`, correcting the stale statements (daily prices, pick and explain calls), and keep only the latest evaluation table in the README with a link to the dated notes; verify no "weekly" or pick-call "rationale" statement remains in the plan

## 7. Verification

- [x] 7.1 Run `uv run pytest`, `uv run pyright` and `uv run --group eval pyright eval`; verify all pass and the characterisation golden files are unchanged since task 1.1, apart from reviewed updates listed in the task that made them
- [x] 7.2 Run the counts script; verify every target in the design.md table is met, and record before and after in the README development section
- [x] 7.3 Run one live report (`uv run research COST --refresh`, about $0.10); verify it completes with four LLM calls when the filing's risk selection is already cached (five on a first run: pick, explain, risk, analyst, writer) and comps-ready under 7 s. Done 2026-10-03: 5.96 s comps-ready, 12.8 s total, $0.074; the run also exposed a racy per-stage cached flag and searches ignoring `--refresh`, both fixed with tests
