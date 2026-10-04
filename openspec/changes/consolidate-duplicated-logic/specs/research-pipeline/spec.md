# Spec Delta

## ADDED Requirements

### Requirement: Every consumer gets the same run outcome
The command line, the evaluation and the offline tests SHALL obtain reports through one shared run procedure. For
the same ticker and inputs, each consumer SHALL receive the same report, or the same terminal error with the same
stage and reason.

#### Scenario: Unknown ticker from two consumers
- **WHEN** a report for `ZZZZQX` is requested from the command line and from the evaluation
- **THEN** both stop with stage "validate" and reason "ticker not found", and neither spends any model or search credit

#### Scenario: Same report offline
- **WHEN** the same recorded inputs and the same scripted model outputs are used through the command-line path and the evaluation path
- **THEN** the two reports are identical apart from generation time and measured durations
