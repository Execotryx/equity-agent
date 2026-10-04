# Proposal

## Why

The comps table and the BUY / HOLD / SELL signal are the core outputs graded in the demo. LLMs must not do the
arithmetic, because invented numbers would discredit the report. Opus 5.5 has no temperature control, so a signal
produced only by the LLM could also change between runs on the same data. This change makes the valuation
comparison and a preliminary signal fully deterministic, testable Python (IMPLEMENTATION_PLAN.md §4.4–4.5,
milestone M2).

## What Changes

- Peer validation rules: equity only, price present, not the target, no duplicate share classes.
- Sector-aware metric sets: general, financials and real estate.
- A comps table with the target row, peer rows, the peer median and the target's premium or discount to the median.
- A five-factor scorecard (valuation, growth, profitability, analyst upside, momentum) that maps to a preliminary
  BUY / HOLD / SELL signal.
- All thresholds in one configuration place.

## Capabilities

### New Capabilities

- `comps-valuation`: peer eligibility, sector-appropriate multiples, medians and relative valuation of the target.
- `signal-scorecard`: deterministic factor scoring and the preliminary signal.

### Modified Capabilities

(none)

## Impact

- New module `scoring.py` and models `CompRow`, `CompsTable`, `FactorScore`, `Scorecard`, `Signal`.
- Thresholds added to `config.py`.
- Pure functions with no network or LLM access. Depends on the data contracts from `add-market-data-layer`.
