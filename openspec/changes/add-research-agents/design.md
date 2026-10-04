# Design

## Context

Benchmarks that drive this design are in IMPLEMENTATION_PLAN.md §2.2:

- Claude latency depends mainly on output length.
- Opus 5.5 effort `medium` doubles latency.
- Opus 5.5 shows its first streamed text after ~11 s; Sonnet 5.5 after ~1 s.

The pipeline diagram is in §4.2, and the agent table is in §4.3. The data and scoring modules come from the two
previous changes.

## Goals / Non-Goals

**Goals:**
- Exactly one LLM call per agent in the normal case, plus at most one re-ask.
- All Claude request construction in one module, so model rules are enforced in one place.
- Offline tests for every agent and the pipeline through a fake Claude client.

**Non-Goals:**
- HTTP/SSE transport (next change); the pipeline exposes an async event iterator instead.
- Multi-turn agent loops, tool calling by the model, or handoffs.
- Prompt caching (system prompts are below the minimum cacheable size; see plan §4.3).

## Decisions

- **Anthropic SDK, not the OpenAI Agents SDK.** There is no tool loop or handoff to benefit from, and the native SDK
  gives first-class effort, refusal and usage fields. Alternative: Agents SDK + `LitellmModel`, rejected (plan §3.1).
- **`llm.py` exposes two functions.**
  - `parse(agent, output_model, system, user) -> (obj, usage)` calls `client.beta.messages.parse` with:
    - `output_format=output_model`;
    - `output_config={"effort": effort}`;
    - `betas=["server-side-fallback-2026-07-01"]` and `fallbacks="default"`;
    - `max_tokens=4000`.
  - `stream(agent, system, user) -> AsyncIterator[str]` uses `client.messages.stream` and reads `text_stream`, then
    `get_final_message()` for usage.

  Both functions:
  - check `stop_reason` (refusal / max_tokens) before reading;
  - acquire a shared `asyncio.Semaphore(settings.llm_concurrency)`;
  - use one `AsyncAnthropic(max_retries=2)` per process. A `Gateway` object owns the client and the semaphore. The
    API lifespan (`add-research-api`) or the CLI creates it, and it is passed to agents, never built per call.
    Measured: a reused connection takes 0.31 s per request, a fresh one 0.73 s.
  - `Gateway.warm()` calls `models.retrieve` for each configured model. This is free, and it opens the TLS
    connection and catches a misspelled model name before the first report.
- **Timeouts per call shape.**
  - Structured calls: `timeout=30.0` per attempt, and an outer `asyncio.timeout(60)` around attempts and retries.
    The measured structured call takes about 7 s at effort `low`.
  - Writer: `anthropic.Timeout(90.0, read=60.0)` per attempt. The SDK is built on `httpx2`, so `httpx` objects must
    never be passed to it (plan §2.4).
  - The SDK default (10 minutes) is never used.
  - A timeout surfaces as `StageError("timed out")`, so the Analyst falls back to the preliminary signal.

  Errors are caught most specific first: `NotFoundError`, `AuthenticationError`, `RateLimitError`,
  `APIStatusError`, `APIConnectionError`. The fallback call shape was verified live during planning (7.2 s,
  plan §2.2).
- **Schemas kept simple for structured outputs:** plain types, `Literal`, lists. Counts, lengths and ranges are
  enforced by each agent's `validate()` and stated in the prompt; they are not encoded as JSON-Schema constraints.
- **Agent base class:** `ClaudeAgent[In, Out]` with a `name`, a system prompt loaded from `prompts/<name>.md`, a
  `build_user(input) -> str` method (compact JSON with `sort_keys=True`) and `validate(out, input) -> list[str]`.
  A generic `run()` performs parse → validate → one re-ask with violations → raise `StageError`.
- **Length caps in prompts.** Exact word limits and item counts appear in each system prompt; this halved latency in
  the benchmark.
- **Writer runs alongside the Analyst.** Its input leaves out the signal, so it never contradicts it. The report's
  conclusion is the Analyst's `signal_reasoning`. The Writer's markdown is split on its four fixed `##` headings.
  The number-grounding check uses a regex over numbers in the prose, compared with a set of formatted numbers derived
  from the input (rounded to 0–2 decimals, with %, B and M variants). Unmatched numbers become quality warnings,
  not failures.
- **Writer model:** `claude-sonnet-5-5` with effort `low` and default (adaptive) thinking. Sonnet 5.5 rejects
  `thinking: disabled`; adaptive at low effort gave first text after ~1 s.
- **Pipeline as an async generator of `PipelineEvent`.** It uses `asyncio.gather` for the branches and an
  `asyncio.Queue` to merge events from concurrent stages. The CLI consumes the same generator, as the API will.
  - Blocking I/O calls run in `asyncio.to_thread`: yfinance, the EDGAR lookup and Tavily.
  - Filing parsing goes through the data layer's process pool (`add-market-data-layer` design), because it is
    CPU-bound and would hold the GIL in a thread.
  - No pipeline coroutine calls a blocking function directly.
- **Comps in two calls: pick, then explain.** Ragas showed peer rationales were the least grounded text (faithfulness
  0.34-0.45): written before the peers' data was fetched, they relied on industry knowledge the search snippets
  lacked. The pick call now returns tickers and names only, which makes it shorter. The explain call runs after the
  peer quotes are fetched (needed for eligibility anyway) and sees each peer's business summary. Cost: one more
  short Opus call per uncached report (about $0.02) on the comps path. Peer choices, including rationales, stay
  cached for 7 days. Considered: one call over a pre-fetched candidate pool, rejected because the candidates aren't
  known before the model proposes them.
- **The explain call is off the critical path.** The comps branch emits the table as soon as it is built and starts
  the explain call as a background task. The scorecard, Analyst and Writer don't use rationales (their payloads
  never included them), so only report assembly awaits the task; a second comps partial carries the rationales.
  Measured before this change: comps-ready rose from 4.8–6.7 s to 7.4–11.6 s with the explain call inline.
- **Static fallback peers** are in `peers_fallback.json`: sector → list of liquid large caps.
- **Price table** (`config.py`): Opus 5.5 $4 / $20, Sonnet 5.5 $2 / $10, Haiku 4.5 $1 / $5 per million tokens.
  It is used only for cost estimates.
- **`FakeClaude` for tests:** it implements the same two functions and returns recorded outputs per agent and
  ticker, or scripted failures (refusal, 429, schema violation).

## Risks / Trade-offs

- [Claude latency over budget on a cold run] → The levers are listed in plan §9.3: lower word caps, per-agent model
  switch in `.env`, and the report cache.
- [Number-grounding regex gives false positives (years, "10-K", item numbers)] → An allow-list of years and
  form-name patterns; warnings only, never failures.
- [Re-asks double cost and latency on a bad response] → At most one re-ask per agent; usage records make it visible.
- [Model refuses a finance prompt] → Server-side fallback first, then a degraded section (the analyst failure falls
  back to the preliminary signal).

- [Opus 5.5 is slower than needed for the extraction-style Comps and Risk agents] → Task 4.2 benchmarks
  `claude-sonnet-5-5` for those two agents against the same validations. It is switched by `.env` only if every
  validation still passes. The Analyst stays on Opus, because its judgement is the point of that stage.

## Open Questions

- The exact heading-split format the Writer reliably follows may need one prompt iteration after the first live run.
  It changes only the prompt, not the specs.
