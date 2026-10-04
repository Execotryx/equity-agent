# Spec Delta

## Purpose

Exposes the research pipeline over local HTTP. Clients can watch a report being built in real time and retrieve
finished reports again without re-running the agents.

## ADDED Requirements

### Requirement: Streamed research run
The API SHALL provide a GET endpoint that takes a ticker and an optional refresh flag. It SHALL respond with an
event stream (`text/event-stream`). Each pipeline event SHALL be sent as a named event — `stage`, `partial`,
`narrative`, `report` or `error` — with a JSON payload. The stream SHALL end after the `report` event or a terminal
`error` event.

A section MAY be sent in more than one `partial` event. Each one SHALL carry the whole section, and a later `partial`
with the same key replaces the earlier one. A fresh comps section SHALL be sent first without peer rationales and
then again with them.

#### Scenario: Successful stream
- **WHEN** a client opens the stream for `AAPL`
- **THEN** it receives `stage` and `partial` events, with the first comps `partial` before any `narrative` event, then exactly one `report` event as the last event, and the connection closes

#### Scenario: Comps sent twice
- **WHEN** a client opens the stream for a ticker whose peers are not cached
- **THEN** it receives a comps `partial` without peer rationales and a later comps `partial` with a rationale for every peer

#### Scenario: Cached report
- **WHEN** a client opens the stream for a ticker with a report cached less than 1 hour ago and refresh not set
- **THEN** it receives the `report` event immediately, without any LLM call

### Requirement: Events are delivered without buffering
Each event SHALL be flushed to the client as soon as the pipeline emits it. The response SHALL disable proxy
buffering and caching.

#### Scenario: Partial before completion
- **WHEN** the comps section is ready 5 seconds into a 15-second run
- **THEN** the client receives the comps `partial` event at about 5 seconds, not at the end of the run

### Requirement: Streams are not compressed
The event stream response SHALL NOT be compressed or otherwise transformed in a way that holds events back.

#### Scenario: Client accepts gzip
- **WHEN** a client that sends `Accept-Encoding: gzip` opens the stream
- **THEN** the response has no content encoding and events still arrive one by one

### Requirement: Warm start
The service SHALL finish start-up work before it accepts requests:

- load the data and model libraries;
- start and warm the filing-parser worker;
- create the shared model client and open its connection.

The health endpoint SHALL report ready only after this work is done. A failure to open the model connection SHALL be
logged as a warning, and it SHALL NOT prevent start-up. Stopping the service SHALL shut down the worker process.

#### Scenario: First report after start
- **WHEN** the first research request arrives after start-up completed
- **THEN** none of its recorded stage timings include library loading or worker start-up

#### Scenario: Health during a run
- **WHEN** a research run is parsing a filing
- **THEN** a health request is answered within 1 second

#### Scenario: Shutdown
- **WHEN** the service is stopped with Ctrl+C
- **THEN** no filing-parser worker process remains running

### Requirement: Validation errors are terminal events
An invalid or unknown ticker SHALL produce a single `error` event with a stage of `validate` and a readable message,
followed by the end of the stream. Section failures from degraded branches SHALL be sent as non-terminal `error`
events, and the stream SHALL continue.

#### Scenario: Unknown ticker
- **WHEN** a client opens the stream for `ZZZZQX`
- **THEN** it receives one `error` event with stage `validate` and message "ticker not found", and the stream ends

#### Scenario: Risk branch fails
- **WHEN** the risk branch fails during a run
- **THEN** a non-terminal `error` event with stage `risk` is sent and a `report` event follows later

### Requirement: Cached report retrieval
The API SHALL provide a GET endpoint that returns the latest cached report for a ticker as JSON. It SHALL return
HTTP 404 with a JSON error body when no unexpired report exists.

#### Scenario: Report exists
- **WHEN** a client requests the cached report for `NVDA` after a successful run
- **THEN** it receives HTTP 200 with a body that validates against the report schema

#### Scenario: No report
- **WHEN** a client requests the cached report for a ticker never researched
- **THEN** it receives HTTP 404 with an error message

#### Scenario: Invalid ticker
- **WHEN** a client requests the cached report for `BAD TICKER!`
- **THEN** it receives HTTP 400 with an error message

### Requirement: One run per ticker at a time
While a run for a ticker is in progress, another stream request for the same ticker SHALL attach to the same run and
receive its remaining events. It SHALL NOT start a second run that spends credits again.

#### Scenario: Double click
- **WHEN** two stream requests for `COST` arrive one second apart
- **THEN** only one pipeline run happens and both clients receive the final `report` event

### Requirement: Client disconnect
If the client disconnects, the run SHALL continue to completion so that its report is cached. No further events
SHALL be written to the closed connection.

#### Scenario: Browser tab closed mid-run
- **WHEN** the client disconnects 5 seconds into a run
- **THEN** the run completes and the report is available from the cached-report endpoint

### Requirement: Local browser access
The API SHALL allow cross-origin requests from the local frontend origin and SHALL reject other origins. Error
responses, including request validation errors, SHALL use a JSON body with a message field and SHALL NOT include
stack traces or secrets.

#### Scenario: Frontend origin
- **WHEN** the frontend at `http://localhost:3000` calls the API
- **THEN** the response carries CORS headers that allow that origin

#### Scenario: Missing parameter
- **WHEN** a client opens the stream without a ticker
- **THEN** it receives HTTP 422 with a JSON body that has a message field
