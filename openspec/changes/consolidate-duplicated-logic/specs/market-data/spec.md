# Spec Delta

## ADDED Requirements

### Requirement: Failure reasons are stable
Every data-layer failure SHALL carry a short reason from a fixed set: "invalid ticker", "ticker not found", "only
individual stocks are supported", or a provider failure. The reason SHALL be available separately from the
human-readable message, and callers SHALL use it without parsing message text. The same reason SHALL be reported
whether the failure happens for the target ticker or for a peer.

#### Scenario: Unknown target and unknown peer
- **WHEN** `ZZZZQX` is requested as a target, and separately as one peer in a batch
- **THEN** the run's terminal error and the peer's exclusion both carry the reason "ticker not found"

#### Scenario: Message wording changes
- **WHEN** the message text of a data error is reworded
- **THEN** the reasons shown in run errors and peer exclusions are unchanged

### Requirement: Recorded fixtures cover every parsed quote field
The quote parser SHALL declare the provider fields it reads, and the fixture recorder SHALL record exactly those
fields. Reading an undeclared field SHALL fail in the offline tests rather than silently returning nothing.

#### Scenario: Parser starts reading a new field
- **WHEN** the quote parser is changed to read a provider field that is not declared
- **THEN** the offline test suite fails until the field is declared, and a declared field is recorded by the next fixture recording
