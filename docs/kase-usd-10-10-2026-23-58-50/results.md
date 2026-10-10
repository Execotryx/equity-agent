# Live KASE test execution

Creation: 10-10-2026-23-58-50 (Asia/Qyzylorda)

Native cases require the named issuer, declared quote currency and a KASE trading venue.
US-listing cases research KASE-listed companies using US symbols; their prices are not KASE prices.
All cases use the production market-data router after app ticker normalization. Supported native USD symbols use KASE; other inputs retain Yahoo routing.

Listing sources: [KASE shares](https://kase.kz/en/investors/instruments/shares), [KASE Global](https://kase.kz/en/markets/kase-global).

| Company | KASE symbol | Input | Currency | Scope | Phase | Result | Failed criteria |
|---|---|---|---|---|---|---|---|
| Halyk Bank | HSBKd | HSBKD | USD | native | quote | PASS |  |
| Kaspi.kz | KSPId | KSPID | USD | native | quote | PASS |  |
| Kazatomprom | KZAPd | KZAPD | USD | native | quote | PASS |  |
| Freedom Holding | FRHC_KZ | FRHC_KZ | USD | native | quote | PASS |  |
| Solidcore Resources | CORE_KZ | CORE_KZ | USD | native | quote | FAIL | quote available: quote unavailable |
| Kaspi.kz | KSPId | KSPI | USD | us_listing | report | PASS |  |
| Freedom Holding | FRHC_KZ | FRHC | USD | us_listing | report | PASS |  |
| Freedom Holding | FRHC_KZ | FRHC_KZ | USD | native | report | PASS |  |

7/8 cases passed. Recorded Claude cost: $0.2095.

Pass/fail follows structural acceptance criteria. A reasoned unavailable risk section is allowed;
narrative quality warnings and performance budgets are diagnostics, not passing criteria.

## Report limitations

- KSPI: no risk-factor section found in the 20-F. Quality warnings: narrative numbers not found in the input: 100, 73, 57, 72. Performance budget: over.
- FRHC: SEC filing unavailable (TypeError). Quality warnings: narrative numbers not found in the input: 55. Performance budget: within.
- FRHC_KZ: SEC filing unavailable (TypeError). Quality warnings: Native KASE annual price history and 52-week range unavailable; momentum is neutral.; EV-based multiples unavailable for native KASE instruments.; narrative numbers not found in the input: 56. Performance budget: over.

Each case JSON preserves checks, timings and observed quote details. Report JSON also includes
the complete research report, acceptance results, model usage/cost and quality warnings.
