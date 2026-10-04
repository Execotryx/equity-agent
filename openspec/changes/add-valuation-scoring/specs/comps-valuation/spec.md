# Spec Delta

## Purpose

Turns a target company and a set of candidate peers into a comparable-companies table. The table uses metrics that
suit the target's sector, medians that ignore missing data, and the target's premium or discount to its peers.

## ADDED Requirements

### Requirement: Peer eligibility
A candidate peer SHALL be included only if it is an equity with a current price, is not the target itself, and is
not another share class of a company already included (for example, only one of `GOOG` and `GOOGL`). Every excluded
candidate SHALL be reported with its exclusion reason.

#### Scenario: Target proposed as its own peer
- **WHEN** candidates for `AAPL` include `AAPL`
- **THEN** `AAPL` is excluded as a peer with reason "is the target"

#### Scenario: Duplicate share class
- **WHEN** candidates include both `GOOGL` and `GOOG`
- **THEN** only the first one is included and the other is excluded with reason "duplicate share class"

### Requirement: Minimum peer count
The comps table SHALL contain at least 3 and at most 5 eligible peers. If fewer than 3 are eligible, the table SHALL
be marked as insufficient so that the caller can obtain more candidates.

#### Scenario: Too few eligible peers
- **WHEN** only 2 of 4 candidates are eligible
- **THEN** the result is marked insufficient and lists the 2 eligible peers and the 2 exclusions

#### Scenario: More than five eligible
- **WHEN** 7 candidates are eligible
- **THEN** the first 5 in candidate order are used

### Requirement: Sector-aware metric set
The system SHALL choose the metric set from the target's sector:

- **financials:** trailing P/E, forward P/E, price-to-book, return on equity, dividend yield, revenue growth;
- **real estate:** trailing P/E, price-to-book, dividend yield, EV/Revenue;
- **general (all other sectors):** trailing P/E, forward P/E, EV/EBITDA, EV/Revenue, net margin, revenue growth,
  debt-to-equity.

Each set SHALL designate one primary valuation multiple:

- forward P/E for general (trailing P/E when forward is missing);
- price-to-book for financials;
- trailing P/E for real estate.

#### Scenario: Bank target
- **WHEN** the target's sector is Financial Services
- **THEN** the table uses the financials set, does not include EV/EBITDA, and the primary multiple is price-to-book

#### Scenario: Technology target
- **WHEN** the target's sector is Technology
- **THEN** the table uses the general set and the primary multiple is forward P/E

### Requirement: Medians ignore missing values
For each metric the peer median SHALL be computed only from peers that have that metric. If no peer has it, the
median SHALL be marked missing. Missing values SHALL never be treated as zero.

#### Scenario: One peer missing a metric
- **WHEN** peers have EV/EBITDA values 20, missing and 30
- **THEN** the EV/EBITDA median is 25

#### Scenario: Negative earnings
- **WHEN** a peer has a negative or missing P/E
- **THEN** that peer is excluded from the P/E median and its P/E is displayed as not meaningful

### Requirement: Relative valuation of the target
For each metric in the set, the system SHALL compute the target's percentage difference from the peer median
(target / median − 1). It SHALL be marked missing when either value is missing or the median is zero or negative.

#### Scenario: Premium to peers
- **WHEN** the target forward P/E is 33 and the peer median is 30
- **THEN** the target is shown at a +10% premium on forward P/E

### Requirement: Comps table content
The comps table SHALL contain:

- the target row (flagged as the target);
- one row per eligible peer, with ticker, name, market capitalisation and the metric-set values;
- the median row;
- the target's percentage differences;
- the metric set used;
- each peer's selection rationale when one is provided;
- the source URLs used for peer discovery.

#### Scenario: Complete table
- **WHEN** a table is built for a target with 4 eligible peers
- **THEN** it has 1 target row, 4 peer rows and a median row, and every row has the same metric columns
