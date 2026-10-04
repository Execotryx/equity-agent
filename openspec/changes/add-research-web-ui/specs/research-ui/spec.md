# Spec Delta

## Purpose

Lets a user request research for a stock ticker in the browser and read the resulting report. Each section appears
as soon as its agent finishes, so progress and partial results are visible in real time.

## ADDED Requirements

### Requirement: Ticker entry
The home page SHALL provide a ticker input and quick-pick buttons for AAPL, NVDA, JPM, COST and TSLA. Submitting SHALL
open the report page for that ticker. Input that is empty or has invalid characters SHALL show an inline message and
SHALL NOT navigate.

#### Scenario: Submit a ticker
- **WHEN** the user types `nvda` and presses Enter
- **THEN** the report page for `NVDA` opens and research starts

#### Scenario: Invalid input
- **WHEN** the user submits `$$$`
- **THEN** an inline validation message is shown and no request is sent

### Requirement: Agent progress display
The report page SHALL show one status card for each pipeline step after validation: financial data, comps, peer
rationales, risk, news, analyst and writer. Each card shows pending, running, done (with duration and a cached
marker), failed or skipped. Cards SHALL update as stage events arrive. When the run ends, a step that never started
(peer rationales when the peers came from the cache) SHALL show skipped, and a report served from the cache SHALL
mark every card as cached.

#### Scenario: Agent completes
- **WHEN** a stage-finished event for the Comps Agent arrives with a duration of 8,400 ms
- **THEN** the Comps card shows done and "8.4 s"

#### Scenario: Peers from the cache
- **WHEN** a run ends without any peer-rationale stage event
- **THEN** the peer-rationales card shows skipped

### Requirement: Progressive rendering
Each report section SHALL render as soon as its partial result arrives, without waiting for the whole report. The
sections are: price header, key financials, price chart, comps table, valuation chart, risk list, recent news and
signal card. Sections not yet available SHALL show a loading placeholder. A later partial for the same section SHALL
replace the earlier one. The final `report` event SHALL replace every section, so a report served from the cache,
which arrives as a single `report` event, renders completely.

#### Scenario: Comps before narrative
- **WHEN** the comps partial result arrives and no narrative has arrived yet
- **THEN** the comps table is visible while the narrative area still shows a placeholder

#### Scenario: Cached report
- **WHEN** the stream delivers only validation stage events and a `report` event
- **THEN** every section, including the narrative, renders from the report

### Requirement: Comps table presentation
The comps table SHALL:

- highlight the target row;
- show a median row;
- format multiples to one decimal place and percentages with a % sign;
- show missing values as an em dash;
- mark the target's premium or discount to the median with an up or down indicator;
- show each peer's rationale on hover or focus, and a "rationale pending" note while the comps section has arrived
  without rationales;
- list the source links used for peer discovery;
- label fallback peers as such.

#### Scenario: Missing metric
- **WHEN** a peer has no EV/EBITDA
- **THEN** its cell shows "—" and the median is unaffected

#### Scenario: Financials metric set
- **WHEN** the report uses the financials metric set
- **THEN** the table shows P/B and ROE columns and no EV/EBITDA column

#### Scenario: Rationales arrive later
- **WHEN** a comps partial without rationales is followed by one with rationales
- **THEN** each peer's rationale becomes available without the table being re-mounted or losing scroll position

### Requirement: Signal card
The signal card SHALL show:

- the final BUY, HOLD or SELL as a colour-coded badge with a text label (colour is never the only cue);
- the confidence;
- the five scorecard factors with their scores and explanations;
- the preliminary signal and, when the analyst changed it, the change reason;
- the thesis points, counterpoints and signal reasoning.

Before the analyst finishes, the card SHALL show the scorecard and the preliminary signal, labelled as awaiting the
analyst.

#### Scenario: Analyst changed the signal
- **WHEN** the preliminary signal is HOLD and the final signal is BUY
- **THEN** the card shows BUY, notes it was changed from HOLD, and displays the change reason

#### Scenario: Scorecard before the analyst
- **WHEN** the scorecard partial has arrived and the analyst partial has not
- **THEN** the card shows the factors and the preliminary signal labelled "awaiting the analyst"

#### Scenario: Analyst unavailable
- **WHEN** the analyst section failed
- **THEN** the card shows the preliminary signal labelled "not reviewed by the analyst"

### Requirement: Streamed narrative
The narrative SHALL render as formatted markdown that grows as narrative fragments arrive, and SHALL show the four
section headings. The disclaimer "Educational project - not investment advice." SHALL always be visible on the
report page.

#### Scenario: Narrative streaming
- **WHEN** narrative fragments arrive
- **THEN** the displayed text grows without a page reload

### Requirement: Errors and partial failures
A validation error SHALL replace the report with a readable message and a link back to the home page. A failed
section SHALL show its reason in place of the section while the rest of the report renders normally; the reason
comes from the section's `error` event during a run, or from the section's error object in the report. If the
connection to the API fails before any event arrives, the page SHALL show that the backend is unreachable and offer a
retry. The page SHALL close the stream after the `report` event or a terminal `error`, so the browser does not
reconnect and start another run.

#### Scenario: Unknown ticker
- **WHEN** the stream returns a validation error "ticker not found"
- **THEN** the page shows that message and a link to try another ticker

#### Scenario: Risk section failed
- **WHEN** the report's risk section is an error with the message "SEC filing unavailable"
- **THEN** the risk list area shows that message and every other section renders

#### Scenario: Backend not running
- **WHEN** the API cannot be reached
- **THEN** the page states that the backend is unreachable and shows a retry button

### Requirement: Refresh and diagnostics
The report page SHALL offer a refresh action that requests a new run that bypasses the cache. It SHALL show when the
report was generated, and SHALL have a collapsible diagnostics panel with per-stage timings, per-agent model, tokens
and estimated cost, cache hits and quality warnings.

#### Scenario: Refresh
- **WHEN** the user clicks refresh on a cached report
- **THEN** a new run starts with refresh enabled and the agent cards reset to pending

### Requirement: Responsive and accessible layout
The report SHALL be usable from 360 px to desktop widths without horizontal page scrolling. Wide tables MAY scroll
inside their own container. Interactive elements SHALL be reachable and operable by keyboard. Charts SHALL have a
text alternative.

#### Scenario: Phone width
- **WHEN** the report is viewed at 375 px width
- **THEN** the page has no horizontal scroll, and the comps table scrolls within its own container
