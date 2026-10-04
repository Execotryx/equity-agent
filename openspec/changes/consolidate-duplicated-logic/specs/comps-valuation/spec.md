# Spec Delta

## ADDED Requirements

### Requirement: One text rendering per metric
Each metric value SHALL be rendered as the same text everywhere it is shown: scorecard explanations, agent inputs,
the comps table printed by command-line tools, and the report views. Percent-like metrics SHALL use one decimal and
a percent sign; debt-to-equity SHALL use two decimals; other multiples SHALL use one decimal; non-meaningful values
(such as a negative P/E) SHALL be shown as not meaningful.

#### Scenario: Debt-to-equity in two places
- **WHEN** a target with debt-to-equity 0.78445 appears in the printed comps table and in an agent's input
- **THEN** both show "0.78"

#### Scenario: Net margin in a scorecard explanation and an agent input
- **WHEN** a target's net margin is 0.27619
- **THEN** the profitability explanation and the agents' input both show "27.6%"
