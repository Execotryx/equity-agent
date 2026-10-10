# Native KASE USD quotes and issuer enrichment

## Problem

Underscore inputs are rejected and Yahoo does not quote the native KASE receipts. Foreign listing reports
cannot establish a native KASE trading price. A USD quote also does not establish USD financial accounts.

## Change

Accept underscore tickers and route explicit native USD symbols to KASE's public website JSON adapter.
Validate identities and enrich through a closed registry of Yahoo listings with verified ISINs and share units.
Keep quote, financial and filing provenance separate across CLI, API, recording, caches and UI.

The user-approved implementation plan authorizes this change. Native annual price-history ingestion,
KZT native quotes, FX conversion, inferred aliases and EV-based native multiples are out of scope.
