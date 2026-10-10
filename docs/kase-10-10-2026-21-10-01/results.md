# Live KASE test execution

Creation: 10-10-2026-21-10-01 (Asia/Qyzylorda)

Native cases require a KASE quote in KZT for the named issuer. US-listing cases research the same
companies traded through KASE Global using their US symbols; their prices are not KASE prices.

Listing sources: [KASE shares](https://kase.kz/en/investors/instruments/shares), [KASE Global](https://kase.kz/en/markets/kase-global).

| Company | KASE symbol | Input | Scope | Result | Failed criteria |
|---|---|---|---|---|---|
| Halyk Bank | HSBK | HSBK | native | FAIL | quote available: ticker not found |
| Kaspi.kz | KSPI | KSPI | native | FAIL | expected quote currency: expected KZT; got USD; expected trading venue: NasdaqGS |
| Kazatomprom | KZAP | KZAP | native | FAIL | quote available: ticker not found |
| KazMunayGas | KMGZ | KMGZ | native | FAIL | quote available: ticker not found |
| KEGOC | KEGC | KEGC | native | FAIL | quote available: ticker not found |
| Kcell | KCEL | KCEL | native | FAIL | quote available: ticker not found |
| Apple | AAPL_KZ | AAPL | us_listing | PASS |  |
| NVIDIA | NVDA_KZ | NVDA | us_listing | PASS |  |
| JPMorgan Chase | JPM_KZ | JPM | us_listing | PASS |  |

3/9 cases passed. Recorded Claude cost: $0.2103.

Pass/fail follows structural acceptance criteria. A reasoned unavailable risk section is allowed;
narrative quality warnings and performance budgets are diagnostics, not passing criteria.

## Report limitations

- AAPL: SEC filing unavailable (TypeError). Quality warnings: narrative: narrative is 452 words (limit 450). Performance budget: within.
- NVDA: SEC filing unavailable (TypeError). Quality warnings: narrative: narrative is 468 words (limit 450); narrative numbers not found in the input: 62, 58, 65. Performance budget: within.
- JPM: SEC filing unavailable (TypeError). Quality warnings: none. Performance budget: within.

Each case JSON preserves checks, timings and observed quote details. US-listing JSON also includes
the complete research report, acceptance results, model usage/cost and quality warnings.
