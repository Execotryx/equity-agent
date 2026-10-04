# Spec Delta

## Purpose

Keeps fetched data and expensive intermediate results on local disk for as long as each kind of data stays valid,
so repeated research runs are fast and spend no API credits.

## ADDED Requirements

### Requirement: Time-bounded entries per data type
The system SHALL cache results with these lifetimes:

- quotes and valuation inputs: 15 minutes;
- financial and price history: 24 hours;
- extracted risk headings: no expiry, keyed by filing accession number;
- web search results: 7 days.

An expired entry SHALL be treated as absent.

#### Scenario: Fresh quote served from cache
- **WHEN** the same ticker's quote is requested twice within 15 minutes
- **THEN** the second request makes no network call

#### Scenario: Expired quote refetched
- **WHEN** a quote is requested more than 15 minutes after it was cached
- **THEN** it is fetched again from the provider

#### Scenario: Risk headings never expire
- **WHEN** risk headings for a filing accession number were cached a month ago
- **THEN** they are served from the cache without downloading the filing

### Requirement: Cache survives restarts
Cached entries SHALL persist on local disk and remain usable after the service restarts.

#### Scenario: Restart
- **WHEN** the service is restarted after caching AAPL data
- **THEN** a request for AAPL within the entry lifetimes makes no network call for the cached parts

### Requirement: Cache bypass
Callers SHALL be able to request fresh data. Fresh data SHALL ignore cached quotes, history and search results, and
SHALL overwrite them with the new values. Risk headings keyed by an unchanged accession number MAY still be served
from the cache.

#### Scenario: Refresh requested
- **WHEN** a quote is requested with refresh enabled
- **THEN** the provider is called even though a fresh cached quote exists, and the cache holds the new value

### Requirement: Cache hits are observable
Each data request SHALL report whether it was served from the cache, so reports can list their cache hits.

#### Scenario: Mixed hits
- **WHEN** a report uses a cached quote and freshly fetched history
- **THEN** the report's cache-hit list contains the quote key and not the history key

### Requirement: Corrupt cache does not break requests
If a cache entry cannot be read or decoded, the system SHALL discard it and fetch fresh data instead of failing.

#### Scenario: Corrupt entry
- **WHEN** a cached value is unreadable
- **THEN** the entry is removed and the data is fetched from the provider
