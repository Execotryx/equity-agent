# Proposal

## Why

The brief requires results "displayed in a readable format" and a live demo. Without a UI, the agents' work is only
visible as CLI output. The web page should also make the multi-agent pipeline visible: agents lighting up as they
finish, and tables appearing before the narrative. That is the clearest demonstration of the architecture. This is
milestone M5 (IMPLEMENTATION_PLAN.md §7).

## What Changes

- A home page with a ticker input and quick-pick chips for the five test tickers.
- A report page that consumes the event stream and progressively renders:
  - agent progress;
  - the price header;
  - key financials and the price chart;
  - the comps table and valuation chart;
  - the risk list and recent news;
  - the signal card with the scorecard (preliminary first, then the analyst's review);
  - the streamed narrative;
  - the disclaimer.
- Loading, partial-failure and error states; a refresh action; a responsive layout down to phone width.

## Capabilities

### New Capabilities

- `research-ui`: the user-facing web experience for requesting and reading a research report.

### Modified Capabilities

(none)

## Impact

- `frontend/src/app/*`, `frontend/src/components/*`, `frontend/src/lib/*` (event types, reducer, stream hook,
  formatting).
- New frontend dependencies: `recharts`, `react-markdown`; dev: `vitest`, `jsdom`, `@testing-library/react`.
- New script `backend/scripts/export_ui_fixtures.py`, which exports real pipeline event sequences for the UI tests.
- Depends on `add-research-api` (endpoints and generated types).
