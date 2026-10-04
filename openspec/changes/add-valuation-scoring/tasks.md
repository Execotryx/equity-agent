# Tasks

## 1. Comps valuation

- [x] 1.1 Add `ScoringConfig` thresholds to `config.py` and the models `CompRow`, `CompsTable`, `PeerExclusion`, `FactorScore`, `Scorecard`, `Signal`; verify with `uv run pyright`
- [x] 1.2 Implement peer eligibility (non-equity, no price, target itself, duplicate share class), returning included peers and exclusions with reasons; verify with table-driven tests for each exclusion reason
- [x] 1.3 Implement sector → metric-set selection and the primary multiple, with forward → trailing P/E fallback; verify with tests for Financial Services, Real Estate, Technology and a missing forward P/E
- [x] 1.4 Implement medians that ignore missing and non-meaningful values, plus the target's percentage differences; verify with tests (20/missing/30 → 25; negative P/E excluded; zero median → missing)
- [x] 1.5 Implement the comps-table builder with the 3–5 peer bounds and the insufficient flag; verify with fixture tests for AAPL (general) and JPM (financials, no EV/EBITDA column)

## 2. Scorecard

- [x] 2.1 Implement the 200-day average and 52-week position helpers from daily closes; verify with a synthetic price-series test
- [x] 2.2 Implement the five factor scorers with "insufficient data" handling and explanations that cite the numbers; verify with table-driven tests at, just inside and just outside every threshold
- [x] 2.3 Implement the total → preliminary signal mapping; verify with tests for totals −2, −1, 0, +1 and +2
- [x] 2.4 Add a determinism test (score the same fixture twice, then compare) and a config-override test (10% valuation band); verify both pass

## 3. Checks

- [x] 3.1 Add a manual demo command `uv run python -m equity_agent.scoring AAPL MSFT GOOGL DELL` that prints the comps table and scorecard from live or cached data; verify it runs for AAPL and JPM peer sets
- [x] 3.2 Run `uv run pytest` and `uv run pyright`; verify both pass offline
