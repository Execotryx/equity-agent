# Spec Delta

## ADDED Requirements

### Requirement: Named run snapshots keep scores, not reports
The evaluation command SHALL accept a snapshot name. When given, it SHALL store that run's per-sample scores and
summary under the name, without copying the reports. Comparing two runs SHALL need only their stored scores. The
reports of the latest run SHALL remain available for re-scoring.

#### Scenario: Snapshot a run
- **WHEN** the evaluation is run with the snapshot name "prompt-fixes"
- **THEN** a "prompt-fixes" snapshot holds the scores and the summary, and no report copies

#### Scenario: Compare two snapshots
- **WHEN** two snapshots are compared
- **THEN** a per-agent and per-ticker table of mean faithfulness and answer relevancy is produced from their scores alone
