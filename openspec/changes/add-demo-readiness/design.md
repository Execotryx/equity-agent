# Design

## Context

The test matrix, performance budget and demo script are in IMPLEMENTATION_PLAN.md §9–10. What exists already:

- `DataLayer.recorded(directory)` reads provider data in the fixture layout (`<T>/info.json`, `income.json`,
  `closes.json`, `filing.json`, `risk_text.txt`, `search_competitors.json`, `search_news.json`).
- `scripts/record_fixtures.py` records that layout for a fixed peer list, into `tests/fixtures/`.
- FakeClaude derives placeholder answers from each agent's input ("Risk 1", "Sells similar products."). These are
  right for tests but not for a demo, so there are no recorded agent answers yet.
- `tests/test_characterisation.py` compares reports built from `tests/fixtures/` with golden files, so those
  fixtures must not change when the demo recording is refreshed.
- `backend/eval/results/` is already the Ragas results folder.
- The API (`create_app`) builds its services in the lifespan, the web UI reads `/api/health`, and `run_report`,
  `clear_agent_caches` and `RunFailed` are the shared runner.

## Goals / Non-Goals

**Goals:**
- A single command answers "is the demo ready?".
- The offline mode exercises the real pipeline and streaming code paths, not a static page.

**Non-Goals:**
- A general LLM-quality evaluation framework or LLM-as-judge scoring; the checks are structural acceptance criteria
  (Ragas covers faithfulness).
- Load or concurrency testing.

## Decisions

- **A demo recording is one live run per ticker, captured whole.** `evaluate --record` runs each report with:
  - the live providers wrapped in recording sources (`demo.py`), which write every provider response, for the
    target and every peer the Comps Agent picked, to `backend/demo/<T>/` in the fixture layout;
  - the Gateway wrapped in a recording client, which writes each agent's validated answer and the Writer's text,
    with their latency, to `backend/demo/<T>/agents.json`;
  - a fresh in-memory cache, so every provider and agent call actually happens and is recorded.

  Because data and answers come from the same run, an offline replay shows the same peers, risks and signal.
  Considered:
  - recording into `tests/fixtures/`: rejected, it would change the golden files;
  - reusing `record_fixtures.py`: rejected, its peer list is fixed and wouldn't match the peers the agent picks.
- **Offline mode = dependency injection at startup.** When `DEMO_OFFLINE=1`, `live_services` returns:
  - `DataLayer.recorded(DEMO_DIR)` with an in-memory cache, using an offline market source that raises
    `NotRecorded` ("not available offline") for a ticker with no recording;
  - a `ReplayClaude` client that serves the recorded answers by ticker (from the agent's input) and output type,
    in recorded order, sleeping each call's recorded time × `DEMO_REPLAY_SPEED` (default 0.4), and streams the
    recorded Writer text in small chunks over the same scaled time. Its usage records cost $0.
  The pipeline, API and UI code are unchanged. Considered: replaying the recorded event stream, rejected because it
  would skip the pipeline; serving cached report JSON, rejected because it skips progressive rendering, which is
  the most visible part of the demo.
- **Offline status** is a field of `/api/health`; the UI header shows an "Offline demo" badge when it is true.
  Keys are still required at start-up, since offline mode is a fallback on the demo laptop.
- **`warm.py` runs the pipeline up to the scorecard**: validation, then the financials, comps (including the
  explain call, since the peer choice is cached only once explained), risk and news branches. It fills the data
  and agent caches without paying for the Analyst and Writer and caches no report. It shares `_Run` with the
  pipeline rather than duplicating the branches.
- **The demo runs on `npm run start:all`, never `dev:all`** (foundation change).
  - `dev:all` reloads the API on any save, which re-imports about 10 s of libraries and restarts the parser worker.
  - `next dev` compiles each page on its first visit.
  - With `start:all`, the first ticker after start-up pays neither cost. IMPLEMENTATION_PLAN.md §10 is corrected.
- **Evaluation runs:**
  - Default: the persistent data cache stays warm, `clear_agent_caches` runs before each ticker, so every agent
    runs live (the budget's "warm data cache" column).
  - `--record`: cold, as above, and writes the recording.
  - It runs through `run_report`; a terminal failure arrives as `RunFailed`, which the `ZZZZQX` check expects.
  - The live checks are pure functions over the report (`acceptance.py`), so they are tested offline with
    FakeClaude reports, including a deliberately broken one.
- **Evaluation output:** `backend/eval/acceptance.md` and `backend/eval/acceptance.json` (not `eval/results.*`,
  which would sit beside the Ragas `results/` folder). Each row is checked against the §9.3 budget (comps ready
  ≤ 12 s, total ≤ 30 s) separately from pass/fail.

## Risks / Trade-offs

- [Offline data looks stale (old prices)] → The UI badge and the generated-at time make it explicit; recorded right
  before the demo.
- [Evaluation spends credits] → It is a manual command and is never run from pytest. Its estimated cost is printed
  before start and its measured cost in the results. A full run is 7 reports (about $0.55) and 14 Tavily credits.
- [Recorded agent answers stop matching after a prompt or payload change] → Replay looks answers up by ticker and
  output type, not by exact prompt, so it keeps working; refresh the recording with `evaluate --record`.
- [A cold `--record` run is slower than a demo report] → It uses the parse worker like the API, so its timings are
  real cold timings; the demo itself runs warm after `warm.py`. A first run that parsed filings inline put JPM at
  40 s, because a parse in the event loop's process holds the GIL and slows every other branch.
