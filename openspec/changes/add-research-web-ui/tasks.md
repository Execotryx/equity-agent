# Tasks

## 1. Data plumbing

- [x] 1.1 Add `recharts`, `react-markdown`, `vitest`, `jsdom` and `@testing-library/react`, with a Vitest config and an `npm test` script; verify `npm run build` and `npx vitest run` succeed
- [x] 1.2 Implement `lib/format.ts` (currency, multiples, percentages, null → "—", matching the backend's `formatting.py`); verify with Vitest unit tests
- [x] 1.3 Add `backend/scripts/export_ui_fixtures.py` and export event fixtures (AAPL fresh, AAPL cached, JPM, unknown ticker, AAPL with a failed risk agent); verify each file ends with a `report` or terminal `error` event
- [x] 1.4 Implement `lib/events.ts`, the reducer in `lib/reportState.ts` and `useResearchStream` (EventSource, close on final events, unreachable detection, refresh); verify with Vitest reducer tests over the fixtures: sections replace on repeated partials, the cached report fills every section, the validation error is fatal, the risk failure is a section error, and peer rationales end skipped when no explain stage ran

## 2. Pages and components

- [x] 2.1 Build the home page with ticker input, client-side validation and quick-pick chips; verify with a component test that `$$$` shows an inline message without navigating, and manually that `nvda` + Enter opens `/report/NVDA`
- [x] 2.2 Build `AgentProgress` (seven cards with pending/running/done/failed/skipped, duration, cached marker); verify with a component test driven by stage events
- [x] 2.3 Build `PriceHeader`, `KeyFinancials` and `PriceChart` (with text alternative); verify they render from the AAPL fixture report
- [x] 2.4 Build `CompsTable` (target highlight, median row, ▲▼ vs median, rationale on hover/focus with a pending note, fallback label, sources) and `ValuationChart`; verify with component tests for the AAPL (general) and JPM (financials) fixtures
- [x] 2.5 Build `RiskList` (severity chips, categories, filing link, unavailable state) and `NewsList`; verify with tests for both risk states
- [x] 2.6 Build `SignalCard` (badge with text label, confidence, factors, preliminary vs final, change reason, "awaiting the analyst" and "not reviewed" states); verify with tests for confirmed, changed, awaiting and analyst-failed states
- [x] 2.7 Build `Narrative` (streaming markdown) and the persistent disclaimer; verify the text grows as fragments arrive in a reducer-driven test
- [x] 2.8 Build the report-page error states (validation error, section errors, backend unreachable with retry), the refresh action, generated-at time and the diagnostics panel; verify each state manually against the running backend

## 3. Polish and checks

- [x] 3.1 Do a visual design pass (use the frontend-design skill), check responsive layout at 375 px and 1440 px, and check keyboard navigation; verify there's no horizontal page scroll at 375 px and every control is reachable by Tab
- [x] 3.2 Run the full flow for AAPL, NVDA, JPM, COST and TSLA against `npm run start:all`; verify tables appear before the narrative and every section renders or shows a reasoned error
- [x] 3.3 Run `npm run build`, `npx tsc --noEmit`, `npm run lint` and `npx vitest run`; verify all pass

## Notes from implementation (2026-10-04)

- 1.1: Vitest 5 needs `@types/node` 22 or later; the scaffold's `^20` was bumped to `^24` to match the installed
  Node 24.
- 2.1, 2.8, 3.1, 3.2: checked in the browser against the live API (`next start` build plus `start:backend`):
  - `$$$` shows the inline message; `nvda` + Enter opens `/report/NVDA`.
  - AAPL, NVDA, JPM, COST and TSLA all rendered every section with no section errors; the comps table appeared
    before the first narrative text each time (1.6–2.5 s with cached peers). JPM showed the financials metric set.
  - Refresh on TSLA reset the cards to Queued, showed the comps table at 6.1 s with "Peer rationales are being
    written…", the narrative from 6.9 s, the rationales at 10.6 s and the report at 13.4 s ($0.075).
  - `ZZZZQX` replaced the report with "ZZZZQX: ticker not found" and a link home. With the API stopped the page
    showed "The research backend is unreachable"; Retry after restarting the API loaded the cached report.
  - 375 px (dark) and 1440 px (light): no horizontal page scroll; the comps table scrolls in its own box. Every
    control is reachable by Tab, and focusing a peer shows its rationale.
- Two bugs found in the browser and fixed:
  - the visually hidden "premium/discount to the median" labels in the comps cells are absolutely positioned and
    escaped the table's scroll box, widening the page to 759 px at 375 px; the scroll box is now `relative`;
  - Recharts' keyboard layer made each chart's `svg` focusable inside an `aria-hidden` wrapper (the caption is the
    text alternative); `accessibilityLayer={false}` removes it.
- Revenue/EBITDA bar labels now sit in a fixed slot, so a long value can't overflow a narrow column.
