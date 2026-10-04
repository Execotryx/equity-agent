# Spec Delta

## ADDED Requirements

### Requirement: Smoke check exercises the service's own provider calls
The smoke check SHALL verify each external service through the same lookup, validation and client code the service
uses at runtime, not through separate calls of its own. A defect in a production lookup SHALL therefore make the
corresponding smoke check fail.

#### Scenario: Filing lookup rule shared
- **WHEN** the service's annual-filing lookup excludes amended filings
- **THEN** the SEC smoke check applies the same exclusion, because it runs that lookup

#### Scenario: Claude check through the gateway
- **WHEN** the smoke check verifies Claude
- **THEN** it confirms every configured model exists and makes one call with the service's own request settings (model, effort and refusal fallback)
