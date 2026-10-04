# Spec Delta

## Purpose

Measures whether the research agents' text is grounded in the data they were given and stays on task, using
Ragas metrics scored by an independent judge model, so that prompt and model changes can be compared on numbers.

## ADDED Requirements

### Requirement: Samples pair agent text with the agent's own input
The system SHALL build evaluation samples from a saved research report. Each sample SHALL contain a task description,
the text an agent produced, and the input data that agent received, reproduced exactly as the agent saw it. The
sample set for one report SHALL be:

- one sample per Writer section (company overview, financial commentary, comps commentary, risk commentary);
- one Analyst sample (valuation summary, thesis, counterpoints and signal reasoning);
- one Risk Agent sample (risk titles and explanations), when the risk section is available;
- one Comps Agent sample (peer rationales), when peers came from the agent.

Sections that failed or were degraded SHALL be skipped and listed as skipped with the reason.

#### Scenario: Complete report
- **WHEN** samples are built from a report with all sections present and agent-selected peers
- **THEN** 7 samples are produced, and each sample's input data equals the input that agent received in that run

#### Scenario: Risk section unavailable
- **WHEN** samples are built from a report whose risk section is an error
- **THEN** the Risk Agent sample is skipped and listed with the reason "risk section unavailable"

### Requirement: Independent judge and metrics
Samples SHALL be scored with Ragas faithfulness (every sample) and answer relevancy (Writer and Analyst samples). The
judge model SHALL be Claude Haiku 4.5, which belongs to a different family than the generator models, at the lowest
sampling temperature it accepts. Answer relevancy SHALL use local sentence embeddings, so no extra API key is needed.

#### Scenario: Supported and unsupported claims
- **WHEN** a Writer section states two figures present in its input and one claim absent from it
- **THEN** the faithfulness score for that sample is below 1 and above 0

#### Scenario: Score not computable
- **WHEN** the judge cannot extract any claim from a sample's text
- **THEN** that sample's faithfulness is recorded as not scored, and it is excluded from averages and counted separately

### Requirement: Evaluation command
The system SHALL provide a command that, for each requested ticker (default AAPL, NVDA, JPM, COST and TSLA):

1. generates a fresh live report, bypassing the report and agent caches, unless asked to reuse saved reports;
2. saves the report;
3. builds and scores its samples.

It SHALL print the estimated cost before starting. One ticker failing SHALL NOT stop the others.

#### Scenario: Reuse saved reports
- **WHEN** the command is run with the reuse option and saved reports exist for all tickers
- **THEN** no research report is generated, and only judge calls are made

#### Scenario: One ticker fails
- **WHEN** report generation fails for one ticker
- **THEN** that ticker is listed as failed with the reason, and the other tickers are scored

### Requirement: Recorded results
The evaluation SHALL write per-sample scores (ticker, agent, section, metric values, judge model, timestamp) as JSON,
and a markdown summary with:

- mean faithfulness and answer relevancy per agent, and per ticker;
- the number of samples not scored;
- the lowest-scoring samples, with the claims the judge found unsupported where available.

A dated note in `docs/` SHALL record the baseline and its caveats.

#### Scenario: Summary written
- **WHEN** an evaluation run completes for five tickers
- **THEN** the JSON file has one entry per scored sample, and the summary has a per-agent table and a per-ticker table

### Requirement: Evaluation stays optional
The app SHALL run, and its offline tests SHALL pass, without the evaluation libraries installed. The evaluation
libraries SHALL be installed only on request.

#### Scenario: Default install
- **WHEN** the backend is installed with the default dependency groups
- **THEN** the evaluation library and its embedding model are not installed, and the offline test suite passes
