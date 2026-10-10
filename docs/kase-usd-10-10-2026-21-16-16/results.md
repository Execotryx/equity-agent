# Live KASE test execution

Creation: 10-10-2026-21-16-16 (Asia/Qyzylorda)

Native cases require the named issuer, declared quote currency and a KASE trading venue.
US-listing cases research KASE-listed companies using US symbols; their prices are not KASE prices.
Native probes apply the app's ticker normalization before calling its Yahoo adapter.

Listing sources: [KASE shares](https://kase.kz/en/investors/instruments/shares), [KASE Global](https://kase.kz/en/markets/kase-global).

| Company | KASE symbol | Input | Currency | Scope | Result | Failed criteria |
|---|---|---|---|---|---|---|
| Halyk Bank | HSBKd | HSBKD | USD | native | FAIL | quote available: ticker not found |
| Kaspi.kz | KSPId | KSPID | USD | native | FAIL | quote available: ticker not found |
| Kazatomprom | KZAPd | KZAPD | USD | native | FAIL | quote available: ticker not found |
| Freedom Holding | FRHC_KZ | FRHC_KZ | USD | native | FAIL | ticker accepted by application: invalid ticker |
| Solidcore Resources | CORE_KZ | CORE_KZ | USD | native | FAIL | ticker accepted by application: invalid ticker |
| Kaspi.kz | KSPId | KSPI | USD | us_listing | PASS |  |
| Freedom Holding | FRHC_KZ | FRHC | USD | us_listing | PASS |  |

2/7 cases passed. Recorded Claude cost: $0.1367.

Pass/fail follows structural acceptance criteria. A reasoned unavailable risk section is allowed;
narrative quality warnings and performance budgets are diagnostics, not passing criteria.

## Report limitations

- KSPI: no risk-factor section found in the 20-F. Quality warnings: narrative numbers not found in the input: 100, 73, 57, 72. Performance budget: within.
- FRHC: SEC filing unavailable (TypeError). Quality warnings: narrative numbers not found in the input: 55, 100. Performance budget: within.

Each case JSON preserves checks, timings and observed quote details. US-listing JSON also includes
the complete research report, acceptance results, model usage/cost and quality warnings.
