# KASE native quote fixtures

Creation: 10-10-2026 (Asia/Qyzylorda). Responses were fetched from
`https://kase.kz/api/instruments/securities/{symbol}/`; only fields used by validation
and quote provenance were retained. Prices and provider timestamps are observations,
not an assertion of ongoing quote availability. `CORE_KZ` was recognized with a null price.

`failure_cases.json` contains protocol fixtures for a 404, unsupported currencies/types,
malformed JSON shapes, timeouts and HTTP 503. Failure variants are synthetic; they do not
claim that an outage or timeout was observed during recording. Runtime tests consume these
fixtures offline and additionally cover invalid JSON, ISIN/issuer mismatches and nonfinite prices.
