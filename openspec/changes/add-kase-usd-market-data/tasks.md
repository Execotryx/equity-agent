# Implementation and validation

- [x] Accept underscore inputs in Python/TypeScript with existing normalization and boundaries.
- [x] Add one production source factory with validated native KASE USD quotes and controlled error classes.
- [x] Register verified issuer names, ISINs, receipt units, private aliases and SEC mappings.
- [x] Preserve native quote price/provenance; enrich issuer financials without trading-history substitution.
- [x] Add currency/provenance contracts, account-currency formatting, valuation adjustments and diagnostics.
- [x] Preserve caching/Refresh, provider response cleanup, recordings, native run keys and peer exclusions.
- [x] Generate TypeScript types and review metadata-only golden/UI fixture changes.
- [x] Execute backend pytest/Pyright and frontend tests/lint/TypeScript/production build.
- [x] Execute fresh USD live evidence, including a native FRHC_KZ full report.
- [x] Update repository guides, specifications and a timestamped change record.

Live result: 7/8 checks passed. CORE_KZ remains recognized without a price, failing live quote availability.
Its controlled handling passes offline. Earlier evidence remains unchanged. Current SEC/parser, narrative
grounding and performance diagnostics are retained in the full live reports rather than counted as successes
for those separate properties. See `docs/kase-usd-10-10-2026-23-58-50/results.md`.
