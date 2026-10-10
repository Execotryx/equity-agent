# Spec Delta

## Purpose

Provides validated, normalised market data for a ticker and its peers: company snapshot, valuation inputs,
financial history and price history, so later stages never call the market data provider directly.

## ADDED Requirements

### Requirement: Ticker input is normalised and validated
The system SHALL convert ticker input to upper case and trim surrounding whitespace. It SHALL reject input that does
not match one letter followed by up to nine letters, digits, dots, underscores or hyphens. It SHALL convert a class-share dot
(for example `BRK.B`) to the provider's hyphen form (`BRK-B`).

#### Scenario: Lower-case input
- **WHEN** the input is ` aapl `
- **THEN** the ticker used for all lookups is `AAPL`

#### Scenario: Class share with a dot
- **WHEN** the input is `brk.b`
- **THEN** the ticker used for lookups is `BRK-B`

#### Scenario: Malformed input
- **WHEN** the input is `$$$` or an empty string
- **THEN** the system returns an "invalid ticker" error without calling any external service

### Requirement: Unknown or non-equity tickers are rejected
The system SHALL treat a ticker as valid only when the market data provider returns a quote type of equity and a
current price. Yahoo instruments without a quote SHALL return a "ticker not found" error. A recognized native
KASE instrument without a positive finite `price` SHALL return "quote unavailable"; unsupported KASE instruments
or currencies SHALL return "unsupported instrument or currency". It SHALL NOT return an empty or partial
snapshot.

#### Scenario: Unknown ticker
- **WHEN** the ticker `ZZZZQX` is requested
- **THEN** the system returns a "ticker not found" error

#### Scenario: Non-equity instrument
- **WHEN** the ticker resolves to an ETF or index
- **THEN** the system returns an error stating that only individual stocks are supported

### Requirement: Company snapshot
For a valid ticker the system SHALL return the company name, sector, industry, currency, current price, market
capitalisation, 52-week low and high, and a business summary of at most 600 characters. Fields the provider does not
supply SHALL be returned as missing, never as zero.

#### Scenario: Snapshot for a large-cap stock
- **WHEN** the snapshot for `AAPL` is requested
- **THEN** it contains a positive price, a positive market capitalisation, sector "Technology" and a non-empty business summary of at most 600 characters

### Requirement: Valuation inputs
The system SHALL return the following when the provider supplies them, and mark each one missing otherwise:
trailing P/E, forward P/E, EV/EBITDA, EV/Revenue, price-to-book, net margin, return on equity, revenue growth,
debt-to-equity, dividend yield, analyst mean target price and analyst recommendation.

#### Scenario: Bank without EBITDA
- **WHEN** valuation inputs for `JPM` are requested
- **THEN** EV/EBITDA is marked missing, and trailing P/E and price-to-book are present

### Requirement: Financial and price history
The system SHALL return up to four fiscal years of annual revenue, EBITDA and net income, and one year of daily
closing prices, in chronological order.

#### Scenario: History for a reporting company
- **WHEN** history for `COST` is requested
- **THEN** at least three annual revenue values and at least 240 daily prices are returned, oldest first

### Requirement: Batch peer fetch
The system SHALL fetch snapshots and valuation inputs for up to five peer tickers concurrently. One peer failing
SHALL NOT fail the batch; failed peers SHALL be reported individually with a reason.

#### Scenario: One invalid peer in a batch
- **WHEN** the peers `MSFT`, `GOOGL` and `ZZZZQX` are fetched together
- **THEN** valid data is returned for `MSFT` and `GOOGL`, and `ZZZZQX` is reported as failed with reason "ticker not found"

#### Scenario: Batch latency
- **WHEN** five valid peers are fetched with an empty cache
- **THEN** the batch completes in less time than fetching them one after another

### Requirement: Provider libraries load before the first request
The market data, SEC and search libraries SHALL be loaded once when the data layer is loaded, not on the first
request. No data request SHALL pay library start-up time.

#### Scenario: First request after loading
- **WHEN** the data layer has been loaded and the first snapshot is requested
- **THEN** no provider library is loaded during that request
