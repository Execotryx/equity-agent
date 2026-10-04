# Spec Delta

## Purpose

Finds a company's latest annual SEC filing and turns its risk-factor section into a compact list of risk headings
that is small enough to give to an LLM on every run.

## ADDED Requirements

### Requirement: Latest annual filing lookup
For a ticker the system SHALL find the most recent annual report filed with SEC EDGAR: a 10-K, or a 20-F for
foreign private issuers. It SHALL return the form type, filing date, accession number and a link to the filing.

#### Scenario: Domestic filer
- **WHEN** the latest annual filing for `AAPL` is requested
- **THEN** the result has form `10-K`, a filing date, an accession number and an SEC URL

#### Scenario: Company with a very large filing history
- **WHEN** the latest annual filing for `JPM` is requested with an empty cache
- **THEN** the lookup step (excluding document download and parsing) completes within 5 seconds

### Requirement: Compact risk-factor headings
The system SHALL extract the risk-factor section of the filing and return it as an ordered list of risk headings,
each a short standalone sentence. It SHALL exclude page footers, item titles and body paragraphs. The returned list
SHALL be at most about 2,000 tokens long; if it is longer, it is truncated at a heading boundary and marked as
truncated.

#### Scenario: Headings for AAPL
- **WHEN** risk headings for `AAPL` are extracted
- **THEN** between 20 and 80 headings are returned, none of them a page footer such as "Apple Inc. | 2025 Form 10-K | 7"

#### Scenario: Oversized section
- **WHEN** the extracted headings exceed the token budget
- **THEN** the list is truncated at a heading boundary and the result is marked as truncated

### Requirement: Filing parsing does not stall the service
Parsing a filing's risk-factor section SHALL run in a separate worker process. The service SHALL start that worker
and load the parsing library in it once, before the first parse. The worker SHALL be reused for later parses. While
a parse is running, the service SHALL keep answering other requests.

#### Scenario: Health check during a long parse
- **WHEN** a JPM-sized risk section is being parsed
- **THEN** a health request made at the same time is answered within 1 second

#### Scenario: Worker is warm before the first parse
- **WHEN** the first parse after service start is requested
- **THEN** it runs in a worker process that already has the parsing library loaded

#### Scenario: Worker crash
- **WHEN** the worker process exits unexpectedly during a parse
- **THEN** that parse returns an "unavailable" result with a reason, and the next parse runs in a new worker

### Requirement: Explicit unavailability
When no 10-K or 20-F exists, or the risk section cannot be extracted, the system SHALL return an "unavailable"
result with a human-readable reason instead of raising an error.

#### Scenario: No annual filing
- **WHEN** risk headings are requested for an issuer with no 10-K or 20-F on EDGAR
- **THEN** the result is "unavailable" with a reason naming the missing filing

### Requirement: SEC access policy
Every request to SEC EDGAR SHALL carry the configured identity, and the system SHALL stay within 10 requests per
second.

#### Scenario: Identity header
- **WHEN** any EDGAR request is made
- **THEN** it carries the configured EDGAR identity
