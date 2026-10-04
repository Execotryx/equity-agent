# Spec Delta

## Purpose

Defines what each research agent receives, what it must return, and the rules its output must satisfy, so that
agent behaviour is testable independently of the model behind it.

## ADDED Requirements

### Requirement: Financial Data Agent
The Financial Data Agent SHALL assemble the target's snapshot, valuation inputs, annual history and price history
into one financial profile without using an LLM.

#### Scenario: Profile for a valid ticker
- **WHEN** the Financial Data Agent runs for `COST`
- **THEN** it returns a financial profile, and no LLM call is recorded for this agent

### Requirement: Comps Agent selects peers
The Comps Agent SHALL work in two calls.

1. **Pick:** it SHALL receive the target's name, sector, industry and business summary, and the competitor-search
   snippets. It SHALL return 3 to 5 distinct US-listed peer tickers, each with a company name. The proposed
   tickers SHALL NOT include the target.
2. **Explain:** after eligibility is checked, it SHALL receive the target's business summary, the business summary,
   sector and industry of each included peer, and the competitor-search snippets. It SHALL return exactly one
   rationale of at most 20 words for each included peer, based on that evidence.

If the explain call fails, the comps table SHALL still be built without rationales, and a quality warning SHALL say so.

#### Scenario: Peers for a retailer
- **WHEN** the Comps Agent runs for `COST` with competitor snippets
- **THEN** the pick call returns 3 to 5 tickers other than `COST`

#### Scenario: Rationales grounded in peer summaries
- **WHEN** the comps table for `COST` has 4 included peers
- **THEN** the explain call receives the business summary of each of the 4 peers and returns one rationale of at most 20 words per peer

#### Scenario: Explain call fails
- **WHEN** the explain call is refused or times out
- **THEN** the comps table is built without rationales and the report lists a quality warning

### Requirement: Comps fallback chain
If fewer than 3 proposed peers pass peer eligibility, the Comps Agent SHALL be asked once more, with the rejected
tickers and reasons listed. If eligibility still fails, the system SHALL complete the set from a static peer list for
the target's sector. The comps table SHALL record which source each peer came from.

#### Scenario: Re-ask succeeds
- **WHEN** the first proposal yields 2 eligible peers and the second yields 4
- **THEN** the comps table is built from the second proposal

#### Scenario: Static fallback used
- **WHEN** both proposals yield fewer than 3 eligible peers
- **THEN** the table is completed from the static sector list and those peers are marked as fallback peers

#### Scenario: No web search available
- **WHEN** competitor search returns no results
- **THEN** the Comps Agent still runs using company context alone

### Requirement: Risk Agent condenses filing risks
The Risk Agent SHALL receive the filing's risk headings and return exactly 6 risks. Each risk SHALL have:

- a title;
- one category: macro, competition, supply chain, regulatory, legal, technology, financial, operational or other;
- a severity from 1 to 3;
- an explanation of at most 30 words;
- the source heading, which SHALL appear verbatim in the provided headings.

#### Scenario: Valid risk selection
- **WHEN** the Risk Agent runs on AAPL's headings
- **THEN** 6 risks are returned and every source heading matches one of the provided headings

#### Scenario: Filing unavailable
- **WHEN** the risk headings are unavailable
- **THEN** the Risk Agent is not called and the risk section reports the unavailability reason

### Requirement: Analyst Agent bounds the signal change
The Analyst Agent SHALL receive the financial profile, comps table, risk selection, scorecard and news headlines. It
SHALL return:

- a final signal;
- a confidence between 0 and 1;
- a valuation summary of at most 60 words;
- exactly 3 thesis points and exactly 3 counterpoints;
- a signal reasoning of at most 80 words.

The final signal SHALL differ from the preliminary signal by at most one step on the SELL–HOLD–BUY scale. A change
SHALL include a stated reason.

#### Scenario: Signal confirmed
- **WHEN** the preliminary signal is HOLD and the analyst returns HOLD
- **THEN** the output is accepted with "changed from preliminary" false

#### Scenario: Two-step change rejected
- **WHEN** the preliminary signal is SELL and the analyst returns BUY
- **THEN** the output fails validation and the agent is re-asked once

#### Scenario: One-step change without reason
- **WHEN** the analyst moves HOLD to BUY without a change reason
- **THEN** the output fails validation and the agent is re-asked once

### Requirement: Writer Agent streams grounded prose
The Writer Agent SHALL stream markdown with exactly four sections: company overview, financial commentary, comps
commentary and risk commentary, at most 450 words in total. Every number in the prose SHALL appear in the Writer's
input data, allowing for rounding. The Writer SHALL NOT state a BUY, HOLD or SELL recommendation.

#### Scenario: Four sections streamed
- **WHEN** the Writer runs for `AAPL`
- **THEN** text arrives incrementally and the final text parses into four non-empty sections

#### Scenario: Invented figure detected
- **WHEN** the final prose contains a number that appears nowhere in the Writer's input
- **THEN** the number is flagged in the report's quality warnings

### Requirement: Educational disclaimer
Every assembled report SHALL include the text "Educational project - not investment advice."

#### Scenario: Disclaimer present
- **WHEN** any report is assembled
- **THEN** it contains the disclaimer text
