# Tasks

## 1. LLM gateway

- [x] 1.1 Implement `llm.py`: a `Gateway` owning one `AsyncAnthropic(max_retries=2)` and the semaphore, `parse()` via `client.beta.messages.parse` with effort and `fallbacks="default"`, `stream()` via `client.messages.stream`, `stop_reason` checks (refusal, max_tokens), and the error mapping chain; verify with tests using a fake transport for success, refusal, truncation, a 429 followed by success, and an unknown model
- [x] 1.2 Add usage records (agent, model, tokens, ms, estimated cost from the price table, request id on failure); verify with a test that a successful fake call yields a correct cost estimate
- [x] 1.3 Implement `FakeClaude` (recorded outputs per agent and ticker, scripted failures) in `tests/fakes.py`; verify it satisfies the same interface under pyright
- [x] 1.4 Add an opt-in live test (`RUN_LIVE_TESTS=1`) that makes one `parse()` call to `claude-opus-5-5` and one `stream()` call to `claude-sonnet-5-5`; verify both succeed and record usage
- [x] 1.5 Add per-shape timeouts (structured: 30 s per attempt, 60 s overall; streamed: 60 s read, 90 s total) and `Gateway.warm()` (`models.retrieve` per configured model); verify with a fake transport that hangs (the stage fails with "timed out" inside the deadline, tested with shortened limits) and with a test that one client instance serves several calls

## 2. Agents

- [x] 2.1 Implement the `ClaudeAgent` base (prompt loading, compact sorted JSON input, validate → one re-ask → `StageError`); verify with tests for pass, pass-on-re-ask and fail-after-re-ask
- [x] 2.2 Implement the Financial Data Agent (deterministic profile assembly); verify that no LLM call is recorded and the profile matches the COST fixture
- [x] 2.3 Implement the Comps Agent with its prompt, the eligibility check, re-ask with rejected tickers, the static fallback and peer-source marking; verify with FakeClaude tests for success, re-ask success, fallback and no-search-results
- [x] 2.4 Implement the Risk Agent with its prompt and validation (exactly 6, valid categories, severity 1–3, verbatim source headings) and skip-on-unavailable; verify with tests including a 5-risk response fixed on re-ask
- [x] 2.5 Implement the Analyst Agent with its prompt and validation (±1 step, change reason, 3 + 3 points, confidence range); verify with tests for confirm, one-step with reason, two-step rejected and missing reason rejected
- [x] 2.6 Implement the Writer Agent (streamed, four headings, ≤ 450 words, no signal in input), the section parser and the number-grounding warnings; verify with tests on recorded streams, including one invented number
- [x] 2.8 Split the Comps Agent into a pick call (tickers and names) and an explain call (one rationale per included peer from the peers' business summaries, sector and industry and the search snippets), with no rationales and a quality warning when the explain call fails; verify with FakeClaude tests for both calls, the explain input containing every included peer's summary, and the failure path, then re-run the Ragas evaluation and record the Comps faithfulness change
- [x] 2.9 Emit the comps table before its rationales and run the explain call in the background, awaited only by report assembly; cache the peer choice once the rationales exist; verify with FakeClaude tests for event order (first comps partial without rationales, scorecard before the explain call ends, second comps partial and report with rationales), the cached path (one comps partial) and explain failure, then re-run the Ragas evaluation and record comps-ready times
- [x] 2.7 Write `prompts/*.md` for the four LLM agents with explicit word and item limits; verify a live opt-in run for AAPL passes all agent validations

## 3. Pipeline and CLI

- [x] 3.1 Implement the async pipeline generator (validation stop, concurrent branches, scorecard, Analyst ∥ Writer, event queue, timings); verify with FakeClaude tests for event order, branch overlap, Analyst/Writer overlap, the validation stop with zero usage, and a 2 s blocking fake fetch in the risk branch that does not delay the financial partial event
- [x] 3.2 Implement degraded handling (risk, news and comps failures; analyst failure → preliminary signal flagged as not reviewed); verify with one test per failure mode
- [x] 3.3 Implement report assembly (all sections, usage, cache hits, quality warnings, disclaimer) and caching of peer selections (7 d), risk selections (no expiry) and reports (1 h) with refresh bypass; verify with tests that a second run within an hour makes no LLM call and that warm agent caches leave only Analyst and Writer calls
- [x] 3.4 Implement `uv run research <TICKER> [--json] [--refresh]` printing sections, timings and total cost; verify the JSON output validates against the `ResearchReport` schema
- [x] 3.5 Document the agent architecture and the Anthropic SDK deviation from the brief in the README; verify the README links to IMPLEMENTATION_PLAN.md §3.1

## 4. Integration check

- [x] 4.1 Run the CLI live for AAPL, NVDA, JPM, COST and TSLA with a warm data cache; verify each report has ≥ 3 peers, 6 risks (or a reasoned unavailability), a valid signal, comps ready ≤ 12 s and total ≤ 30 s, and record timings and cost in `README.md`
- [ ] 4.2 Benchmark `claude-sonnet-5-5` for the Comps and Risk agents (`COMPS_MODEL`, `RISK_MODEL`) on the same five tickers with agent caches bypassed; verify by recording per-agent latency, validation pass rate and cost for both models in `README.md`, and switch the defaults only if Sonnet passes every validation
- [x] 4.3 Run `uv run pytest` and `uv run pyright`; verify both pass offline
