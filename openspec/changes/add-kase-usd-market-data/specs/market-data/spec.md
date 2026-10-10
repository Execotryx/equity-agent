# Spec Delta

## ADDED Requirements

### Requirement: Production routing and quote provenance
The system SHALL route suffix `_KZ` and `HSBKD`, `KSPID`, `KZAPD` to KASE. All other inputs retain Yahoo.
It SHALL GET `https://kase.kz/api/instruments/securities/{symbol}/` with a ten-second timeout and validate
the returned symbol, issuer, type (ordinary share or depositary receipt), and USD currency. Mapped native
issuers SHALL additionally match registered names and instrument ISINs. Source symbol casing, source URL,
exchange/provider and provider timestamp SHALL accompany the quote without inventing a timezone.

#### Scenario: Underscore input
- **WHEN** ` frhc_kz ` is submitted
- **THEN** form navigation, SSE, run registry, cache and KASE provider request preserve `FRHC_KZ`

#### Scenario: Recognized but unquoted
- **WHEN** CORE_KZ has a null, nonpositive or nonfinite `price`
- **THEN** the result is `quote unavailable`, with no fallback to close, bids/offers or another exchange

#### Scenario: Unknown, unsupported or failed provider
- **WHEN** KASE returns 404, an unsupported instrument/currency, or a malformed response/outage/timeout
- **THEN** the respective result is `ticker not found`, `unsupported instrument or currency`, or `provider error`

### Requirement: Explicit issuer enrichment and units
The registry SHALL map FRHC_KZ/FRHC, KSPID/KSPI, HSBKD/HSBK.IL, KZAPD/KAP.IL,
AAPL_KZ/AAPL, NVDA_KZ/NVDA, JPM_KZ/JPM; CORE_KZ has no enrichment. The registry SHALL retain verified
issuer names, expected ISINs, units and supporting source URLs. Halyk units are 40 common shares for both
GDRs; other initial mappings use matching one-share units. Private Yahoo identifiers SHALL be passed verbatim.
Enrichment SHALL supply issuer descriptions, sector, annual financials and unitless ratios while preserving
the native KASE price. Failure SHALL retain the native quote and a diagnostic.

#### Scenario: KZT financial accounts behind a USD receipt
- **WHEN** HSBKD, KSPID or KZAPD has verified KZT accounts
- **THEN** histories are labelled/formatted in KZT in UI and agent input; no FX conversion occurs
- **AND** P/E, forward P/E, P/B and dividend yield are unavailable for the native target

#### Scenario: Unknown financial currency
- **WHEN** the reporting currency is missing in a new provider response
- **THEN** monetary history is omitted with a diagnostic, while legacy saved reports remain readable

### Requirement: Native valuation and history boundaries
For verified USD accounts and compatible units, let `u = native shares / source shares` and
`r = native price / (source price * u)`. The system SHALL scale P/E, forward P/E and P/B by `r`, dividend
yield by `1/r`, verified USD capitalization by `r`, and verified USD analyst targets by `u`. Targets SHALL
be labelled cross-listing estimates. Unsupported account currencies/units SHALL not supply price-sensitive
ratios. All native KASE EV multiples SHALL be missing. Native annual prices and 52-week ranges SHALL be
missing and momentum SHALL remain visibly neutral; foreign trading history SHALL never substitute.

### Requirement: Shared workflows and backward compatibility
CLI, API, recording and live probes SHALL use the production source factory. Native and alias cache keys
SHALL remain separate with existing TTLs and Refresh behavior. HTTP responses SHALL close on success/failure.
Mapped eligible US issuers SHALL use their SEC aliases and preserve FilingRef provenance; others SHALL have
an explicit unavailability reason. Target aliases SHALL be excluded from peers, including failed quotes.
Optional model provenance/currency defaults SHALL load older reports, and TypeScript types SHALL be generated.
Existing endpoint paths and SSE event names SHALL remain unchanged.

### Requirement: Live evidence remains honest
Fresh USD execution SHALL preserve earlier evidence, distinguish native quotes/reports from US-listing
reports, and retain complete report, checks, usage and diagnostics. Missing live prices SHALL fail availability
acceptance even when the separate controlled-error regression passes offline.
