# Spec Delta

## ADDED Requirements

### Requirement: Composite lookups report every cache key they served
A data lookup that combines several cached entries SHALL report each cache key it served from the cache. Examples
are a batch of peer quotes, or a filing lookup followed by its risk headings. A report's cache-hit list SHALL
contain every such key, whichever lookup produced it.

#### Scenario: Warm peer batch and filing
- **WHEN** a report is generated while two of its peer quotes, the filing reference and the risk headings are cached
- **THEN** the report's cache-hit list contains both peer quote keys, the filing key and the risk-headings key
