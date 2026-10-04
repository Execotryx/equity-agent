# Spec Delta

## Purpose

Defines the single, guarded way the service calls Claude models: typed outputs, explicit effort, refusal and error
handling, bounded concurrency, and transparent token and cost accounting.

## ADDED Requirements

### Requirement: Typed structured outputs
Every non-streaming agent call SHALL request output that conforms to the agent's declared schema. The call SHALL
return a validated typed object. A response that does not conform SHALL be treated as a failed call, never passed on
as raw text.

#### Scenario: Valid structured response
- **WHEN** the Risk Agent's call returns content matching its schema
- **THEN** the caller receives a validated risk-selection object

#### Scenario: Truncated response
- **WHEN** a response stops because it reached the output token limit
- **THEN** the call fails with a "truncated output" error and no partial object is returned

### Requirement: Explicit model and effort per call
Every call SHALL use the model and effort level configured for its agent. Calls SHALL NOT send sampling parameters
(temperature, top-p, top-k) and SHALL NOT request that thinking be disabled.

#### Scenario: Default Analyst call
- **WHEN** the Analyst Agent runs with default configuration
- **THEN** the request uses model `claude-opus-5-5`, effort `low` and no sampling parameters

### Requirement: Refusal handling
Calls SHALL enable server-side refusal fallback. When the final response still reports a refusal, the call SHALL fail
with a readable "model declined the request" error that includes the refusal category when one is given. No output
SHALL be read from a refused response.

#### Scenario: Final refusal
- **WHEN** a response has stop reason "refusal"
- **THEN** the agent stage fails with "model declined the request" and the pipeline continues with that stage degraded

### Requirement: Retries and timeouts
Rate-limit, overload, server and connection errors SHALL be retried at most twice with backoff. Each structured
call attempt SHALL time out after 30 seconds, and each streamed attempt after 60 seconds without its first text or
90 seconds in total. Including retries, one structured call SHALL give up within 60 seconds. Invalid requests and
authentication errors SHALL NOT be retried. An unknown model identifier SHALL produce an error that names the
misconfigured model setting.

#### Scenario: Hung structured call
- **WHEN** the model service accepts an Analyst request but never responds
- **THEN** the call fails with a timeout error within 60 seconds, and the pipeline continues with the preliminary signal

#### Scenario: Transient rate limit
- **WHEN** the first attempt returns HTTP 429 and the second succeeds
- **THEN** the call returns the second result

#### Scenario: Unknown model
- **WHEN** an agent's model setting names a model that does not exist
- **THEN** the call fails without retry, with an error naming that agent's model setting

### Requirement: Connections are reused
The service SHALL create one model client per process and reuse it, and its open connections, for every agent call.
The service SHALL be able to open the connection ahead of the first report with a request that costs no tokens.

#### Scenario: Consecutive calls
- **WHEN** the Comps Agent and then the Analyst Agent make calls in the same process
- **THEN** both calls go through the same client, and no client is created per call

#### Scenario: Pre-warmed connection
- **WHEN** the connection was opened ahead of time and the first agent call is made
- **THEN** that call does not include connection setup time

### Requirement: Bounded concurrency
The service SHALL run at most a configured number of Claude calls at the same time (default 4). Additional calls
SHALL wait instead of failing.

#### Scenario: Burst of calls
- **WHEN** six agent calls are started at once with a limit of 4
- **THEN** at most 4 are in flight at any moment and all six complete

### Requirement: Usage and cost accounting
For every call the service SHALL record:

- the agent name and model;
- the input and output token counts;
- the elapsed time;
- an estimated cost in USD, from a configured per-model price table;
- the provider request id when the call fails.

#### Scenario: Successful call recorded
- **WHEN** the Comps Agent call completes
- **THEN** a usage record with model, input tokens, output tokens, milliseconds and estimated cost is attached to the report

### Requirement: Application validation with one re-ask
After schema validation, each agent's output SHALL be checked against its business rules. On the first failure the
call SHALL be repeated once, with the violated rules stated in the request. A second failure SHALL fail the stage
with the list of violations.

#### Scenario: Rule violation corrected on re-ask
- **WHEN** the first Risk Agent response contains 5 risks instead of 6 and the re-ask returns 6 valid risks
- **THEN** the stage succeeds with the second response, and both calls appear in the usage records
