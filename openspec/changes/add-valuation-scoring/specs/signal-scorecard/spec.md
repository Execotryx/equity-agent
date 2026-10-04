# Spec Delta

## Purpose

Produces a repeatable, explainable preliminary BUY / HOLD / SELL signal from five measurable factors. The same input
data always yields the same signal, which the analyst agent may then adjust within strict limits.

## ADDED Requirements

### Requirement: Five scored factors
The system SHALL score five factors, each as −1, 0 or +1, with a one-line explanation that cites the numbers used:

1. **Valuation:** the target's primary multiple vs the peer median. More than 15% below the median scores +1;
   more than 15% above scores −1; otherwise 0.
2. **Growth:** the target's revenue growth vs the peer median. More than 5 percentage points above scores +1;
   more than 5 points below scores −1; otherwise 0.
3. **Profitability:** the target's net margin vs the peer median (return on equity for financials). More than
   5 points above scores +1; more than 5 points below scores −1; otherwise 0.
4. **Analyst upside:** mean target price / current price − 1. Above +10% scores +1; below −10% scores −1;
   otherwise 0.
5. **Momentum:** +1 when the price is above its 200-day average and in the upper half of its 52-week range;
   −1 when it is below its 200-day average and in the lower half; otherwise 0.

A factor whose inputs are missing SHALL score 0 with the explanation "insufficient data".

#### Scenario: Expensive but fast-growing target
- **WHEN** the target's primary multiple is 40% above the peer median and its revenue growth is 20 points above the median
- **THEN** valuation scores −1 and growth scores +1, and each explanation cites the values used

#### Scenario: Missing analyst target
- **WHEN** no analyst mean target price is available
- **THEN** analyst upside scores 0 with the explanation "insufficient data"

### Requirement: Preliminary signal mapping
The preliminary signal SHALL be BUY when the factor total is +2 or more, SELL when it is −2 or less, and HOLD
otherwise.

#### Scenario: Total of +2
- **WHEN** the factor scores are +1, +1, 0, 0, 0
- **THEN** the preliminary signal is BUY

#### Scenario: Total of −1
- **WHEN** the factor scores are −1, 0, 0, 0, 0
- **THEN** the preliminary signal is HOLD

### Requirement: Deterministic output
Given identical inputs, the scorecard SHALL produce identical factor scores, explanations and signal.

#### Scenario: Repeated scoring
- **WHEN** the same comps table and financial profile are scored twice
- **THEN** both scorecards are equal

### Requirement: Configurable thresholds
All factor thresholds (15% valuation band, 5-point growth and profitability bands, 10% upside band, ±2 signal
cut-offs) SHALL be configuration values, and changing them SHALL NOT require code changes in the scoring logic.

#### Scenario: Narrower valuation band
- **WHEN** the valuation band is configured as 10% and the target is 12% below the median
- **THEN** valuation scores +1
