# Design

## Context

Motivation and the bank EBITDA finding are in proposal.md and IMPLEMENTATION_PLAN.md §2.1. This change consumes the
`Snapshot`, `Multiples` and `FinancialProfile` models from `add-market-data-layer`. It is consumed by the agents
change (the Comps Agent supplies candidates; the Analyst Agent receives the scorecard).

## Goals / Non-Goals

**Goals:**
- Pure, side-effect-free functions that are fully covered by table-driven tests.
- Output models that the frontend can render directly.

**Non-Goals:**
- Choosing peers (Comps Agent) and adjusting the signal (Analyst Agent) are in the next change.
- DCF or any forward-looking valuation model.

## Decisions

- **Sector mapping by yfinance `sector` string:**
  - "Financial Services" → financials;
  - "Real Estate" → real_estate;
  - everything else → general.
  Considered: GICS codes, which yfinance doesn't provide reliably.
- **Duplicate share-class detection:** same company name after normalisation (lower-case, suffixes such as
  "Class A" / "Inc." stripped), or a known pair list (`GOOG/GOOGL`, `BRK-A/BRK-B`, `FOX/FOXA`, `NWS/NWSA`).
  Name normalisation alone misses some cases, so both are used.
- **Median with `statistics.median`** on non-missing, meaningful values (P/E ≤ 0 is treated as not meaningful).
- **Percent fields stored as fractions** (0.10), formatted only in the UI. Growth and margin bands compare in
  percentage points on fractions (0.05).
- **Momentum needs the 200-day average.** It is computed from the 1-year daily closes provided by the market-data
  capability; the frontend may downsample them for the chart.
- **Thresholds live in a frozen `ScoringConfig` dataclass inside `config.py`**, injectable in tests.

## Risks / Trade-offs

- [A single primary multiple oversimplifies valuation] → The Analyst Agent sees the whole table and may adjust the
  signal by one notch (next change). The method is documented in the UI.
- [Negative-earnings companies (e.g. early-stage) get valuation 0 from missing P/E] → Documented as "insufficient
  data". EV/Revenue is still shown in the table.
