# Spec Delta

## Purpose

Provides bounded web search for competitor discovery and recent company news, with predictable credit usage and
graceful degradation when the search service is unavailable.

## ADDED Requirements

### Requirement: Competitor search
Given a company name and industry, the system SHALL run one basic-depth web search for the company's competitors. It
SHALL return at most 5 results, each with title, URL, source domain and a content snippet of at most 600 characters.

#### Scenario: Competitor search for a known company
- **WHEN** competitors of "Costco Wholesale" in "Discount Stores" are searched
- **THEN** between 1 and 5 results are returned, each with a URL and a snippet

### Requirement: Recent news search
Given a company name, the system SHALL run one basic-depth news search limited to the past 30 days. It SHALL return
at most 5 headlines with URL, source domain and publication date when available.

#### Scenario: News for a large company
- **WHEN** news for "NVIDIA" is requested
- **THEN** at most 5 items are returned, each with a headline and URL

### Requirement: Search budget per report
The system SHALL use at most two web searches per research report: one competitor search and one news search.
Neither SHALL use a paid "advanced" depth.

#### Scenario: Full report
- **WHEN** a report is generated with an empty cache
- **THEN** no more than two web search requests are sent

### Requirement: Graceful search failure
When the search key is missing, the quota is exhausted, or the service fails, the system SHALL return an empty
result with a reason ("quota exhausted", "not configured", "service error"). It SHALL NOT raise an error to the
caller, and the reason SHALL NOT contain the API key.

#### Scenario: Quota exhausted
- **WHEN** the search service reports that the usage limit is exceeded
- **THEN** the result is empty with reason "quota exhausted"
