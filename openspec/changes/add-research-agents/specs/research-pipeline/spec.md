# Spec Delta

## Purpose

Orchestrates the research agents into one fast, fault-tolerant run per ticker. It emits progress as it goes and
produces a complete, cacheable research report usable from the command line and, later, the API.

## ADDED Requirements

### Requirement: Stage order and concurrency
A run SHALL proceed in this order:

1. Validate the ticker and take a snapshot.
2. Run four branches concurrently: comps (search, Comps Agent, peer data, comps table); risk (filing headings,
   Risk Agent); financial profile; news.
3. Compute the scorecard.
4. Run the Analyst Agent and the Writer Agent concurrently.
5. Assemble the report.

#### Scenario: Branches overlap
- **WHEN** a report is generated
- **THEN** the recorded start times of the comps, risk, financial and news branches all precede the end time of the earliest-finishing branch

#### Scenario: Analyst and Writer overlap
- **WHEN** the scorecard is ready
- **THEN** the Analyst and Writer stages both start before either of them finishes

### Requirement: Blocking work does not stall progress
Blocking data fetches SHALL run outside the event loop, and filing parsing SHALL run in a separate worker process.
Progress events from one branch SHALL NOT wait for blocking work in another branch.

#### Scenario: Slow data fetch in one branch
- **WHEN** the risk branch's data fetch blocks for 2 seconds and the financial profile is ready after 0.1 seconds
- **THEN** the financial partial-result event is emitted before the risk branch finishes

### Requirement: Validation failure stops the run
If ticker validation fails, the run SHALL stop immediately with the validation error. No agent SHALL be called and
no web search SHALL be spent.

#### Scenario: Unknown ticker
- **WHEN** a run is requested for `ZZZZQX`
- **THEN** the run ends with "ticker not found" and no LLM or web-search usage is recorded

### Requirement: Degraded branches
A failure in the risk, news or comps branch SHALL NOT fail the run. The report SHALL contain an error entry for that
section with a readable reason, and later stages SHALL proceed with the data available. If the comps branch fails,
the valuation, growth and profitability factors score 0 with "insufficient data".

#### Scenario: SEC unavailable
- **WHEN** the risk branch fails
- **THEN** the report is produced with a risk-section error and a valid signal

#### Scenario: Analyst fails
- **WHEN** the Analyst Agent fails after its re-ask
- **THEN** the report uses the preliminary signal, marks the analyst section as failed, and states that the signal was not reviewed

### Requirement: Progress events
A run SHALL emit ordered events:

- stage started and stage finished (with duration in milliseconds and whether the result was cached);
- partial results as soon as each section is ready (snapshot, financials, comps, risks, scorecard, analyst);
- narrative text fragments while the Writer streams;
- a final report event, or a terminal error event.

#### Scenario: Early partial results
- **WHEN** the comps table is complete while the Writer has not started
- **THEN** a partial-result event for comps is emitted before any narrative fragment

### Requirement: Comps table before its rationales
The comps partial result SHALL be emitted as soon as the table is built, before the peer rationales are written. When
the rationales arrive, a second comps partial result SHALL carry the same table with the rationales. The comps-ready
time SHALL be measured at the first comps partial result. The scorecard, Analyst and Writer SHALL NOT wait for the
rationales, and the final report SHALL include them.

#### Scenario: Two comps events
- **WHEN** a run explains its peers with a call that takes 2 seconds
- **THEN** a comps partial without rationales is emitted first, the scorecard partial follows without waiting for the explain call, and a later comps partial and the final report contain the rationales

#### Scenario: Cached peers
- **WHEN** the peers and their rationales come from the cache
- **THEN** a single comps partial with the rationales is emitted

### Requirement: Report content and diagnostics
The final report SHALL contain:

- the generation time and ticker;
- the financial profile, comps table, risk selection, news, scorecard, analyst view and narrative (each section
  either a result or an error);
- per-stage timings in milliseconds;
- per-agent usage records with estimated cost;
- the list of cache hits;
- any quality warnings;
- the disclaimer.

#### Scenario: Complete report
- **WHEN** a run succeeds for `AAPL`
- **THEN** the report has all listed sections, a timing entry for every stage and a usage record for every LLM call

### Requirement: Agent output and report caching
The system SHALL cache:

- Comps Agent peer selections for 7 days, keyed by ticker and model;
- Risk Agent selections without expiry, keyed by filing accession number and model;
- complete reports for 1 hour, keyed by ticker.

A refresh request SHALL bypass the report and peer caches.

#### Scenario: Reopen within an hour
- **WHEN** a report for `NVDA` is requested 10 minutes after one was generated
- **THEN** the cached report is returned without any LLM call or web search

#### Scenario: Warm agent caches
- **WHEN** a report for `AAPL` is regenerated after the report cache expired, but within 7 days
- **THEN** the Comps and Risk Agents are not called, and only the Analyst and Writer make LLM calls

### Requirement: Performance budget
With a warm data cache and no cached agent outputs, the run SHALL deliver the comps partial result within 12 seconds
and the final report within 30 seconds for the five demo tickers on the development laptop. Every report SHALL record
the timings needed to check this.

#### Scenario: Demo ticker within budget
- **WHEN** a report for `COST` is generated with a warm data cache
- **THEN** the recorded comps-ready time is at most 12 seconds and the total is at most 30 seconds

### Requirement: Command-line access
The system SHALL provide a command that runs the pipeline for one ticker. It SHALL print a readable report with
stage timings and total estimated cost, and SHALL support JSON output and a refresh option.

#### Scenario: JSON output
- **WHEN** the command is run for `JPM` with the JSON option
- **THEN** standard output is a single JSON document that validates against the report schema
