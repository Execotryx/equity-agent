# Proposal

## Why

A redundancy review after the evaluation work (2026-10-03) found the same logic written several times across the
backend (about 3,650 lines). Some duplicates have already diverged, and some hide bugs:

- **Six failure types.** "What failed and why" is carried in six ways. Two call sites recover the reason by splitting
  exception messages on `":"`, so rewording a message silently changes what users see.
- **Repeated bookkeeping in the pipeline.** It has 15 `except` blocks, 8 hand-written cache-hit records and 10
  hand-written usage records. Data lookups return cache hits under two conventions.
- **Three copies of "run a report and get the result"** (CLI, evaluation, tests), plus a fourth copy of comps
  assembly in the scoring demo.
- **Two number formatters that already disagree.** Debt/equity shows as "0.8" in one and "0.78" in the other.
- **Ticker cleaning hand-written three times** instead of calling the validated normaliser.
- **Field lists kept twice that can drift.** The fixture recorder's quote fields, the cached peer choice versus the
  comps table, and the agents' model names versus the settings.
- **A smoke check that re-implements production calls.** Its filing lookup lacks the amendment filter that broke
  TSLA, so it passed while the real code was broken.
- **A stale design document.** The data-contract section of IMPLEMENTATION_PLAN.md still says weekly prices and
  peer rationales in the pick call. The README repeats the evaluation tables.
- **Evaluation snapshots that copy full reports** (about 950 KB in three folders), although comparison needs only
  the scores.

Next comes the API change, which must stream the same run, map the same terminal errors and report the same
cache hits. It is cheaper to consolidate now than to build a fourth caller on top of the duplicates.

## What Changes

- **One failure vocabulary.**
  - Data errors carry a stable reason, separate from the message.
  - Every expected absence (no filing, no risk section, search not possible) is the same "unavailable" result.
  - Agent failures carry their kind and usage.
  - No caller parses error messages.
- **One way to record cache hits:** every data lookup reports the cache keys it served, including the composite
  lookups (peer batch, filing and headings).
- **Pipeline plumbing in one place:** a stage helper that degrades a failed section and records usage, so branches
  keep only their own logic.
- **One report runner,** used by the CLI, the evaluation and the tests. The comps assembly is shared by the
  pipeline's cached path and the scoring demo, and scorecard printing by the CLI and the demo.
- **One formatting module** for metrics, money, percentage changes and word-boundary truncation, used by the
  scorecard, agent inputs and every printed view.
- **One ticker normaliser** for all ticker input, including model-proposed peers.
- **Field lists with one source:**
  - the quote parser declares the provider fields it reads, and the recorder records exactly those;
  - the cached peer choice is derived from and applied to the comps table;
  - agent models come from settings.
- **A smoke check that calls the production code paths** for filings, quotes, search and the Claude gateway.
- **Test infrastructure in one place:** shared run helpers, a fake Claude client that dispatches on the requested
  output type, and an indexed fixture search.
- **Named evaluation snapshots** that keep scores and summaries only. The existing three snapshot folders migrate
  to that layout.
- **Documentation with one source of truth:** IMPLEMENTATION_PLAN.md §5 points to `models.py`, and the README keeps
  the latest evaluation table and links to the dated notes.

Behaviour is preserved apart from the changes listed under Capabilities below. A characterisation test, recorded
before any refactoring, proves it.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

These capabilities are introduced by earlier changes that are complete but not yet archived. The deltas below add
requirements to them, so this change is archived after those changes.

- `service-configuration` (from `setup-project-foundation`): the smoke check uses the service's own provider calls.
- `market-data` (from `add-market-data-layer`): stable failure reasons; recorded fixtures cover every field the
  quote parser reads.
- `data-cache` (from `add-market-data-layer`): composite lookups report every cache key they served.
- `comps-valuation` (from `add-valuation-scoring`): one text rendering per metric everywhere it is shown.
- `research-pipeline` (from `add-research-agents`): every report consumer gets the same outcome and terminal-error
  reasons.
- `ragas-evaluation` (from `add-ragas-evaluation`): named, score-only run snapshots.

## Impact

- **Backend modules touched:**
  - `models.py`, `cache.py`, `pipeline.py`, `cli.py`, `scoring.py`, `smoke.py`;
  - `data/market.py`, `data/search.py`, `data/sec.py`, `data/fixtures.py`;
  - `agents/agents.py`, `agents/payloads.py`;
  - `evaluation/samples.py`, `eval/run_ragas.py`, `scripts/record_fixtures.py`.
- **New module:** `formatting.py`.
- **Tests:** a new `tests/conftest.py` gets the shared helpers, and `tests/fakes.py` is simplified. A new
  characterisation test is added.
- **Report schema:** unchanged. `ResearchReport` already stores the search failure as plain text (`news_error`),
  so only the data layer's internal search result changes shape. The report is the contract the API and UI will
  consume, which is why this change lands before `add-research-api`.
- **Removed:** the copied `reports/` folders in the three evaluation snapshots (about 950 KB of generated JSON). Their
  scores and summaries move to `backend/eval/runs/<name>/`.
- **Cost:** no Anthropic credit for the refactor. Verification includes one live smoke check (under $0.01) and one
  live report (about $0.10).
- **Depends on:** `add-market-data-layer`, `add-valuation-scoring`, `add-research-agents` and
  `add-ragas-evaluation`. Must land before `add-research-api`.
