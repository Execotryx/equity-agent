# Spec Delta

## Purpose

Makes the live demo dependable and measurable. Caches are warmed ahead of time, an offline fallback can serve
recorded results, and an evaluation shows that every test ticker meets the acceptance criteria within the
performance budget.

## ADDED Requirements

### Requirement: Cache warm-up
The system SHALL provide a command that takes one or more tickers and, for each, fetches and caches:

- market data, financial history and peers;
- the filing risk headings;
- search results;
- the Comps Agent's peer choice with its rationales, and the Risk Agent's selection.

It SHALL NOT run the Analyst or Writer agents or cache a report, and it SHALL drop a cached report for the ticker,
so the next report streams live.

It SHALL print per-ticker success or failure with timings. One ticker failing SHALL NOT stop the others.

#### Scenario: Warm the demo tickers
- **WHEN** the warm-up runs for AAPL, NVDA, JPM, COST and TSLA
- **THEN** a subsequent report for JPM makes no SEC filing download and calls only the Analyst and Writer agents

#### Scenario: Partial failure
- **WHEN** one ticker in the warm-up list is invalid
- **THEN** it is reported as failed and the remaining tickers are warmed

### Requirement: Offline demo mode
When offline mode is enabled, the system SHALL serve reports only from a recording of earlier live runs: the
provider data and the agents' answers, recorded together so they match. It SHALL make no network calls to market
data, SEC, search or LLM services. Offline mode SHALL run the same pipeline and stream the same events, so the UI
behaves as in a live run, with model calls taking a fraction of their recorded time and costing nothing. It SHALL
return a clear error for tickers without a recording. The health endpoint SHALL report whether offline mode is on,
and the UI SHALL display an "Offline demo" badge while it is.

The offline recording SHALL be kept apart from the test fixtures, so refreshing it never changes test results.

#### Scenario: Recorded ticker offline
- **WHEN** offline mode is on and a report for AAPL is requested
- **THEN** a report is streamed from recorded data, no external request is made, and the UI shows the "Offline demo" badge

#### Scenario: Unrecorded ticker offline
- **WHEN** offline mode is on and a report for a ticker without recorded data is requested
- **THEN** the run ends with an error stating that the ticker is not available offline

#### Scenario: Recording before the demo
- **WHEN** the evaluation runs in record mode
- **THEN** the provider data and agent answers of each live run are saved as the offline recording, and an offline report for a recorded ticker shows the same peers, risks and signal as the recorded live run

### Requirement: Acceptance evaluation
The system SHALL provide an evaluation command that generates live reports for AAPL, NVDA, JPM, COST and TSLA and the
edge cases `ZZZZQX`, `BRK.B` and `TSM`. Every agent SHALL run live in each report (agent caches are cleared first).
The command SHALL print its estimated cost before starting. It SHALL check each report against the acceptance
criteria:

- price and key financials present;
- at least 3 peers with at least 2 valuation multiples each;
- a BUY, HOLD or SELL signal with reasoning;
- the risk section present, or unavailable with a reason;
- the disclaimer present.

For edge cases it SHALL check the expected handling instead: a not-found error, class-share resolution, and a
foreign-filer risk section or a reasoned unavailability.

#### Scenario: Matrix passes
- **WHEN** the evaluation runs with working services
- **THEN** every test ticker and edge case is reported as pass or fail with the failed criteria named

#### Scenario: Bank-specific check
- **WHEN** JPM is evaluated
- **THEN** the evaluation also checks that the financials metric set was used and that EV/EBITDA is absent

### Requirement: Evaluation results are recorded
The evaluation SHALL write a markdown results table and a JSON file. For each ticker they SHALL contain:

- pass/fail;
- the signal;
- the number of peers;
- comps-ready time and total time;
- LLM calls and estimated cost.

They SHALL also contain run totals and whether each run met the performance budget.

#### Scenario: Results file
- **WHEN** an evaluation completes
- **THEN** a results table with one row per ticker and a totals row is written, and its timings are taken from each report's recorded timings

#### Scenario: Budget
- **WHEN** a report's comps were ready after more than 12 seconds or the report took more than 30 seconds
- **THEN** its row is marked as over budget, separately from pass/fail

### Requirement: Demo runbook
The project SHALL document the demo procedure:

- the pre-demo warm-up;
- the start command, which SHALL be the demo start command (pre-built frontend, backend that doesn't reload),
  never the development command;
- waiting for start-up to complete before the first ticker;
- the ticker order and talking points;
- how to refresh the offline recording and switch to offline mode if a service fails.

#### Scenario: Following the runbook
- **WHEN** the runbook steps are followed on the development laptop
- **THEN** all five demo tickers display complete reports, and switching to offline mode serves recorded reports

#### Scenario: First ticker after start
- **WHEN** the application was started with the demo start command and start-up has completed
- **THEN** the first report's stage timings are within the performance budget, with no library loading or page compilation added
