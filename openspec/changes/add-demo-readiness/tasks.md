# Tasks

## 1. Warm-up

- [x] 1.1 Implement `uv run python -m equity_agent.warm <TICKERS...>` running stages up to the scorecard (with the explain call), with per-ticker results and timings; verify with a FakeClaude test that a following run calls only the Analyst and Writer, and that an invalid ticker doesn't stop the others

## 2. Offline mode

- [x] 2.1 Implement the recording sources and recording client, and `ReplayClaude`; verify with a test that records a FakeClaude run on fixture data into a temporary folder and replays it with the same peers, risks and signal
- [x] 2.2 Add the `DEMO_OFFLINE` and `DEMO_REPLAY_SPEED` settings and the offline services in `live_services`; verify with a test that blocks network access (socket patch) and still streams a full AAPL report through the API
- [x] 2.3 Return a clear "not available offline" error for unrecorded tickers; verify with a test
- [x] 2.4 Expose offline status in `/api/health` and show an "Offline demo" badge in the UI header; verify with an API test, a component test, and manually with the API started with `DEMO_OFFLINE=1`

## 3. Evaluation

- [x] 3.1 Implement the acceptance checks (`acceptance.py`) and `uv run python -m equity_agent.evaluate [--record]` for the 5 tickers and the edge cases `ZZZZQX`, `BRK.B` and `TSM` (including the JPM financials checks), printing an estimated cost before starting; verify with an offline test using FakeClaude reports that one deliberately broken report fails with the criterion named
- [x] 3.2 Write `eval/acceptance.md` and `eval/acceptance.json` with per-ticker rows, totals and budget compliance taken from report timings; verify the file structure in the same offline test
- [x] 3.3 Run the evaluation live with `--record`; verify all rows pass (or each failure is explained and fixed by prompt or threshold tuning), and put the results table in the README

## 4. Runbook and final checks

- [x] 4.1 Write the demo runbook in the README (warm-up, start with `npm run start:all` and wait for "Application startup complete", ticker order AAPL → JPM → NVDA vs COST → unseen ticker, diagnostics panel, refreshing the recording, offline switch) and correct IMPLEMENTATION_PLAN.md §10; verify by doing one full rehearsal from a cold start following only the runbook
- [x] 4.2 Run `uv run pytest`, `uv run pyright`, `npm run build`, `npx vitest run` and `npm run lint`; verify all pass

## Notes from implementation (2026-10-04)

- 3.3, first `--record` run: 8/8 passed, but JPM (40.3 s), BRK-B (36.7 s) and TSM (30.1 s) were over the 30 s
  budget. Record mode parsed filings inline, holding the GIL in the API's process; it now uses the parse worker
  like the API, with one set of services for the whole run. `Recording.start` no longer deletes the target's folder
  (an earlier target may have recorded it as a peer); only its `agents.json` is cleared.
- 3.3, second `--record` run (cold): 8/8 pass, comps tables in 4.8–8.8 s; JPM 30.0 s, TSM 36.8 s and BRK-B 44.0 s
  were still over. Stage timings (now kept per row) show the cause: the risk branch's first filing download, parse
  and Risk call (22–36 s) gates the Analyst and Writer. Paid once per filing; `warm.py` pays it before a demo.
  Cold results are kept in `eval/acceptance-cold.{md,json}`, separate from the plain run.
- 3.3, after `warm.py` (warm data cache, every agent live): 8/8 pass, 0 over budget, comps 2.0–4.7 s, reports
  14.7–17.2 s, $0.70 for 7 reports. The printed estimate was raised from $0.08 to $0.10 per report.
- 4.1 rehearsal from the runbook (warm-up, start, AAPL, JPM, NVDA, COST, unwarmed MSFT, Diagnostics, offline):
  - warmed reports streamed live in 6.8–7.9 s with tables under 0.5 s; JPM showed P/B and ROE; NVDA (all factors
    +1, BUY) and COST (mixed, HOLD) contrasted as the runbook says;
  - MSFT cold: price 0.4 s, comps 6.6 s with rationales pending, rationales 10.7 s, report 23.2 s, $0.095;
  - offline TSLA: badge shown, streamed in 7.2 s at $0, same peers and signal as the recorded run.
- Found during the rehearsal and fixed:
  - the plain evaluation caches each report for an hour, so demo tickers would open instantly from the cache
    without showing live progress; `warm.py` now drops a cached report for each ticker it warms (spec updated);
  - offline, a ticker recorded only as another's peer (MSFT) was accepted as a target and would have produced a
    broken report; a report now needs a recorded run (`agents.json`), via a `peer_quote` hook in `MarketData`;
    the page explains which tickers are recorded.
- Not run literally: `npm run start:all` itself. The rehearsal used the same two servers (`start:backend` and
  `next start` on a fresh build) through the preview tooling.
