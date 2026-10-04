# Proposal

## Why

"Works in a live demo" is an acceptance criterion. Several things can go wrong live:

- a cold JPM 10-K parse takes about 17 s;
- Wi-Fi or an API can fail;
- the brief's test tickers have never been checked together.

This change adds:

- cache pre-warming;
- an offline mode that can serve the demo from recorded data;
- a repeatable evaluation of the five test tickers against the acceptance criteria and the performance budget.

This is milestone M6 (IMPLEMENTATION_PLAN.md §8–10).

## What Changes

- A warm-up command that pre-fetches data, filing headings and agent outputs for a list of tickers.
- An offline demo mode that replays a recording of live runs (provider data and agent answers, captured together)
  through the real pipeline without network access, and is clearly labelled in the UI.
- An evaluation command that runs the test matrix (AAPL, NVDA, JPM, COST, TSLA plus edge cases). It checks each
  report against the acceptance criteria and writes a results table with timings and cost. Its record mode refreshes
  the offline recording.
- A demo runbook in the README.

## Capabilities

### New Capabilities

- `demo-readiness`: pre-warming, offline demo mode, and the acceptance evaluation of the test tickers.

### Modified Capabilities

(none)

## Impact

- New modules `warm.py`, `demo.py` (recording and replay), `acceptance.py` and `evaluate.py`; `DEMO_OFFLINE` and
  `DEMO_REPLAY_SPEED` settings; an `offline` field in `/api/health`; an offline badge in the UI header.
- New folder `backend/demo/` (the offline recording), kept apart from `backend/tests/fixtures/`.
- `README.md` gains the evaluation results and the demo runbook; IMPLEMENTATION_PLAN.md §10 is corrected to
  `start:all`.
- A full evaluation run spends about $0.55 of Anthropic credit and 14 Tavily credits.
- Depends on all previous changes.
