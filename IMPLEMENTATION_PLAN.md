# Autonomous Equity Research Agent — Implementation Plan

> Capstone Project 3, solo build. The user enters a ticker; five agents produce a research report with key
> financials, a peer comps table, 10-K risk factors and a BUY / HOLD / SELL signal with reasoning.
> Plan written 2026-10-01 and revised the same day to use **Claude models through the Anthropic Python SDK**.
> Every latency figure below was **measured on this laptop** (i7-1185G7, 4 cores, Iris Xe, 32 GB RAM,
> Windows 11) during planning, not taken from documentation.
>
> **Implementation specs:** the plan is broken into 7 OpenSpec changes under `openspec/changes/`, one per milestone.
> Each has a proposal, delta specs, a design and tasks, and all pass `openspec validate --all --strict`. Apply them
> in order: `setup-project-foundation` → `add-market-data-layer` → `add-valuation-scoring` → `add-research-agents`
> → `add-research-api` → `add-research-web-ui` → `add-demo-readiness`.

---

## 1. Goals and constraints

| Requirement (from the brief) | How this plan meets it |
|---|---|
| User enters a ticker | Next.js page with a ticker input; also a CLI for testing |
| Current price and key financials | yfinance `Ticker.info` + annual income statement |
| ≥ 3 comparable companies with valuation multiples | Comps Agent: Tavily search → Claude picks 3–5 tickers → yfinance multiples, computed in Python |
| BUY / HOLD / SELL with reasoning | Deterministic scorecard + Analyst Agent (Claude) explanation |
| Readable output | Structured UI (tables, chart, badges) + narrative written by the Writer Agent |
| Works in a live demo | Disk cache, pre-warm script, recorded offline fixtures as a fallback |
| **Extra: agent performance, runs locally, no VPS** | Whole app runs on the laptop; only LLM inference and search are remote APIs. Targets in §9.3 |
| **Extra: Anthropic models and SDK welcome** | Claude via the official `anthropic` SDK is the LLM layer (§3.1) |

Scope is sized for **one developer**: one backend language (Python), one LLM provider, one SDK, no infrastructure
beyond two local processes.

---

## 2. Investigation results (measured)

### 2.1 Data sources

Library versions resolved on 2026-10-01: `anthropic 1.11.0` (on `httpx2`), `yfinance 1.7.0`, `edgartools 5.59.1`,
`tavily-python 0.8.4`, `fastapi 0.142.2`, `curl-cffi 0.16.3`, `pandas 3.0.6`, `pydantic 2.13.5`
(`openai-agents 0.22.3` was evaluated too, see §3.1).

| Operation | Time | Notes |
|---|---|---|
| yfinance `Ticker("AAPL").info`, cold | 1.9–4.5 s | 183 fields: price, market cap, P/E, EV/EBITDA, EBITDA, margins, growth, analyst target, sector, business summary |
| same, repeated in process | 0.2 s | yfinance keeps an in-process cache |
| `.info` for 5 peers, sequential / 5 threads | 3.3 s / **2.0 s** | Use a thread pool |
| `income_stmt`, `quarterly_income_stmt`, `history(1y)` | ~1.0–1.2 s each | |
| Unknown ticker (`ZZZZQX`) | 1.0 s | **Does not raise.** Returns `{'trailingPegRatio': None}` → validate explicitly |
| JPM `.info` | — | **`ebitda` and `enterpriseToEbitda` are `None`** for banks → sector-aware multiples |
| edgartools `Company(...).get_filings(form="10-K").latest()` for JPM | **27 s** | JPM has a huge filing history (structured notes) |
| same with `trigger_full_load=False` | **0.08 s** | Always pass this flag |
| 10-K HTML download | ~1.3 s | JPM 12.9 MB, COST 1.4 MB, NVDA 2.0 MB |
| `tenk.risk_factors` parse | AAPL 2.2 s, COST 2.5 s, NVDA 3.4 s, **JPM 17 s** | CPU-bound HTML parse, not cached by edgartools between calls |
| Risk factor text size | 42k–115k chars (**10k–28k tokens**) | Too large to send whole on every run |
| Heading-only extraction (short standalone lines) | AAPL: 68k → 5.6k chars (~1.4k tokens) | 12× smaller prompt; headings are the risks themselves |

### 2.2 LLM inference: local vs. cloud, and which Claude configuration

All rows use the same analyst prompt built from live data (AAPL + 4 peers + 10-K risk headings, ~2.6k tokens of
content; Claude counts ~3.9k with its tokenizer and the schema) and a Pydantic structured output with
`signal`, `confidence`, `valuation_summary`, `thesis`, `key_risks`, `comps_commentary`.

| Engine / configuration | Wall time | Output tokens | Signal for AAPL |
|---|---|---|---|
| Ollama `lfm2.5:8b-a1b`, CPU only | **110 s** | 415 | BUY |
| Ollama `granite4.2` 8.8B, CPU only | **> 8 min, timed out** | — | — |
| Gemini `gemini-3.5-flash-lite` (Agents SDK) | 2.5–4.3 s | 380–560 | BUY |
| Gemini `gemini-3.5-flash` (Agents SDK) | 10.1 s | 669 | HOLD |
| `claude-haiku-4-5`, free-form length | 17.7 s | 965 | HOLD |
| `claude-sonnet-5-5`, effort `low`, free-form length | 13.3 s | 1,235 | HOLD |
| `claude-opus-5-5`, effort `low`, free-form length | 16.5 s | 1,231 | HOLD |
| `claude-opus-5-5`, effort `medium` (model default), free-form length | 28.9 s | 2,408 | HOLD |
| **`claude-opus-5-5`, effort `low`, length-capped prompt** | **7.1 s** | 510 | HOLD |
| `claude-sonnet-5-5`, effort `low`, length-capped prompt | 6.5 s | 582 | HOLD |
| `claude-haiku-4-5`, length-capped prompt | 6.3 s | 393 | HOLD |
| 3 × `claude-opus-5-5` `low` concurrently (`asyncio.gather`) | 16.9 s total (each ~16 s) | — | parallel calls don't slow each other |
| `claude-opus-5-5` `low` via `client.beta.messages.parse` + `fallbacks="default"` | 7.2 s | — | same as without fallbacks |
| Streaming prose, `claude-opus-5-5` `low`: first text / total | **11.2 s** / 32.9 s | 2,888 | — |
| Streaming prose, `claude-sonnet-5-5` `low`: first text / total | **1.1 s** / 13.6 s | 1,868 | — |

"Length-capped prompt" = the same prompt plus *"every string at most 35 words; thesis and key_risks exactly 3 items"*.

**What the numbers say**

1. **A local model is not viable on this hardware.** One call takes 2 minutes or more. "Run locally" means the *app* runs on the laptop, and inference is a remote API.
2. **For Claude, output length matters more than model choice.** Generation runs at ~60–100 tokens/s. Capping output length cut Opus 5.5 from 16.5 s to 7.1 s. With capped output, Opus, Sonnet and Haiku all finish in 6–7 s. Every Claude agent in this plan therefore has a tight output schema and explicit length limits.
3. **Opus 5.5 effort `medium` (its default) doubles latency** with no change in the signal. The plan sets `effort: "low"` explicitly on every call and raises it only if the evaluation in M6 shows a quality gap.
4. **Opus 5.5 always thinks before writing**: it cannot turn thinking off, so streamed prose shows its first text after ~11 s. Sonnet 5.5 shows text after ~1 s. This affects only the streaming Writer, which therefore uses Sonnet 5.5 (§4.3).
5. **Quality signal.** AAPL trades at $330 against a $328 mean analyst target and a P/E of 37. Every Claude configuration said HOLD; Gemini flash-lite said BUY. Claude's answer is the more defensible one for this data.
6. Claude is roughly 2× slower per call than Gemini flash-lite. The architecture hides most of that with parallelism, streaming and early rendering of data tables (§4).

### 2.3 External API limits and cost

- **Anthropic API (paid, per token).** Opus 5.5 costs $4 per million input tokens and $20 per million output tokens; Sonnet 5.5 costs $2 / $10; Haiku 4.5 costs $1 / $5. A report makes about 4 calls with roughly 15k input and 3–4k output tokens in total, so **about $0.12–0.15 per report on Opus 5.5** (about half that on Sonnet 5.5). Budget about $10–20 for the whole build and testing phase. Rate limits depend on the account tier and are shown in the Claude Console. The SDK retries 429 and 5xx errors automatically.
- **Tavily free plan.** You get 1,000 credits a month, and a basic search costs 1 credit ([credits](https://docs.tavily.com/documentation/api-credits)). The plan uses at most 2 basic searches per report, so about 500 reports a month. Cached results cost nothing.
- **SEC EDGAR.** No key is needed, but every request must declare a User-Agent identity (`set_identity("Name email")`), and the limit is 10 requests per second.
- **Yahoo Finance.** The API is unofficial and can throttle requests. Mitigations: `curl_cffi`, caching and threaded batches.

### 2.4 Windows pitfalls found

1. **MAX_PATH breaks `curl_cffi`.** In a deeply nested venv the DLL import fails ("The filename or extension is too long"). yfinance then silently falls back to `requests` and prints a rate-limit warning. At `capstone/backend/.venv` (88 characters) it loads correctly. **Do not nest the project deeper**, or enable Windows long paths.
2. The console code page shows `�` for Unicode characters in 10-K text. Set `PYTHONUTF8=1` (in `.env` and the launch scripts) and always write files with `encoding="utf-8"`.
3. PowerShell needs `Set-ExecutionPolicy -Scope Process Bypass` for venv scripts (as in your other projects).
4. `anthropic` 1.x is built on `httpx2`, not `httpx`. Never pass `httpx` objects (timeouts, clients) to the SDK. Use `anthropic.Timeout` / `DefaultAsyncHttpxClient`.

---

## 3. Tech stack decision

### 3.1 Agent layer: native Anthropic SDK instead of the OpenAI Agents SDK

The brief names the OpenAI Agents SDK, and the week 2 base project uses it. Two ways to run Claude were evaluated:

| | **A. Anthropic SDK, code-orchestrated (chosen)** | B. OpenAI Agents SDK + Claude via `LitellmModel` |
|---|---|---|
| Structured output | `client.messages.parse(output_format=PydanticModel)` → validated `parsed_output` | Agents SDK `output_type` translated through LiteLLM |
| Claude-specific controls | `output_config.effort`, refusal `stop_reason`, server-side `fallbacks`, prompt caching, usage fields: all first-class | Passed through LiteLLM's mapping, if supported at all |
| Streaming | `client.messages.stream()` → `text_stream`, `get_final_message()` | `Runner.run_streamed` events via LiteLLM |
| Extra dependencies | `anthropic` only | `openai-agents`, `litellm` (large) and their version coupling |
| What the Agents SDK would add | — | Tool loop, handoffs, tracing. **This pipeline uses none of them**: the order is fixed, data tools run in code before each agent, and each agent makes exactly one LLM call |

**Decision: A.** Each "agent" is a small Python class with a role-specific system prompt, a Pydantic input,
a Pydantic `output_format`, a model and an effort level. The orchestrator in `pipeline.py` runs them in a fixed order.
This keeps the brief's **Researcher → Analyst → Writer** pattern and its five named agents. It drops a framework
whose features this design doesn't use. Fewer moving parts is the right trade for a solo build.
Document the deviation in the README in one paragraph ("the brief suggests the OpenAI Agents SDK; Anthropic
models were explicitly welcome for this project, so the agents call Claude through its own SDK").

**Not used: Claude's server-side `web_search` tool.** It could replace Tavily for peer discovery, but Tavily is a
required part of the stack in the brief. Keep it as a possible later experiment.

### 3.2 Full stack

| Layer | Choice | Why |
|---|---|---|
| LLM | **Claude Opus 5.5** (`claude-opus-5-5`) for the Comps, Risk and Analyst agents; **Claude Sonnet 5.5** (`claude-sonnet-5-5`) for the streamed Writer; `effort: "low"`, length-capped outputs | Opus: strongest current model, ~7 s per call when output is capped, most defensible signal in the benchmark. Sonnet for the Writer: first streamed text in ~1 s instead of ~11 s. Model and effort are configured per agent in `.env`, so any agent can switch to `claude-sonnet-5-5` / `claude-haiku-4-5` without code changes (see §12) |
| LLM SDK | **`anthropic` 1.x**, `AsyncAnthropic` client | Official SDK; `messages.parse` for typed outputs, `messages.stream` for the Writer, built-in retries |
| Market data | **yfinance 1.7** + **curl-cffi** | Free, no key; all needed multiples in one call |
| SEC filings | **edgartools 5.x** | Free; `TenK.risk_factors`, XBRL financials; supports 10-K and 20-F |
| Web search | **tavily-python** | Required by the brief; LLM-optimised snippets for peer discovery and news |
| Backend API | **FastAPI** + uvicorn, Server-Sent Events via `StreamingResponse` | Python is needed for yfinance/edgartools; SSE streams agent progress to the UI |
| Cache | **SQLite** (stdlib `sqlite3`, one file) + edgartools local cache dir | Zero infrastructure, survives restarts, per-entry TTL |
| Python tooling | **uv**, Python 3.13, pytest, pyright | Same as your previous projects |
| Frontend | **Next.js 16** (App Router) + **TypeScript** + **Tailwind CSS v4** | Required stack (Calorie Tracker) |
| Charts / markdown | **Recharts** (price line, multiples bar chart), **react-markdown** | Small, React-native |
| Run both | One `npm run dev:all` (`concurrently` starts uvicorn and `next dev`) | No Docker, no VPS |

**Rejected:**

- **Local LLMs** as the primary engine (§2.2).
- **A second LLM provider** such as Gemini. It is about 2× faster per call and free, but a second SDK means a second structured-output path and a second set of failure modes to test alone. It can be revisited only if Claude latency misses the targets after M6.
- **Next.js API routes** for data fetching: TypeScript has no equivalents of yfinance or edgartools.
- **LangGraph / CrewAI**: they add another framework and nothing this design needs.
- **Redis / Postgres**: unnecessary for one user on one laptop.

---

## 4. Architecture

### 4.1 Performance principles

1. **LLMs only where judgement is needed.** Fetching data and calculating multiples is Python. Claude picks peers, ranks risks, explains the signal and writes prose. It never does arithmetic, so numbers cannot be hallucinated.
2. **Short outputs.** Generation time dominates Claude latency (§2.2). Every schema has bounded lists and every prompt states word limits. Tables are rendered by the UI from data and are never written by the LLM.
3. **`effort: "low"` everywhere** unless the evaluation proves a stage needs more.
4. **Parallelise independent work.** The Comps, Risk and Financial Data branches run concurrently with `asyncio.gather`. Blocking libraries run in `asyncio.to_thread`. The Writer runs **at the same time as** the Analyst (§4.2).
5. **Small prompts.** Agents receive compact JSON (≈ 2–4k tokens), never raw 10-K text or full `info` dicts.
6. **One LLM call per agent.** Data tools are called by code before the agent runs, so there are no tool-call round trips.
7. **Cache everything for as long as it stays valid** and pre-warm the demo tickers.
8. **Show data as soon as it exists.** The price header, financials and comps table appear after the first ~10 s. The signal and narrative stream in afterwards.

### 4.2 Pipeline

```text
ticker
  │
  ▼ Stage 0  validate + snapshot (yfinance .info; quoteType == EQUITY, price present)        ~2 s, no LLM
  │          → UI: price header
  │
  ├───────────────────────────────┬──────────────────────────────┬────────────────────────┐
  ▼ A. Comps Agent                ▼ B. Risk Agent                ▼ C. Financial Data Agent ▼ D. News (optional)
  Tavily "<name> competitors"     edgartools latest 10-K/20-F    income_stmt (4y),         Tavily news, 1 credit
  → Claude picks 3–5 tickers      → heading extraction (cached)   price history 1y,
  → validate + yfinance peers     → Claude: top 6 risks,           key metrics
  → multiples computed in code      category + severity           (no LLM)
  ~8–9 s, 1 LLM call              ~6 s warm, 1 LLM call            ~1.5 s                    ~1.5 s
  └───────────────────────────────┴──────────────────────────────┴────────────────────────┘
  │          → UI: financials, comps table, valuation chart, risk list
  ▼ Stage 2  scorecard (Python): target vs peer median, growth, margins, analyst upside, momentum → preliminary signal
  │
  ├──────────────────────────────────────────┬──────────────────────────────────────────────┐
  ▼ Stage 3a Analyst Agent (1 LLM call)       ▼ Stage 3b Writer Agent (1 LLM call, streamed)
  confirms or moves the signal by one notch   overview, financial, comps and risk commentary
  with a stated reason; thesis, counterpoints (signal-independent sections, so it doesn't wait)
  ~7 s → UI: signal card                      first text ~1 s, done ~10–14 s → UI: narrative
  └──────────────────────────────────────────┴──────────────────────────────────────────────┘
  ▼ ResearchReport (JSON): the conclusion section comes from the Analyst's `signal_reasoning`
```

Critical path, cold cache: 2 s (snapshot) + ~9 s (slowest branch) + max(Analyst ~7 s, Writer ~10–14 s)
≈ **21–25 s for the full report**, with **tables visible at ~11 s** and **the signal at ~18 s**. Reopening a report
within an hour is instant (report cache). JPM's first-ever run adds ~17 s of 10-K parsing; the pre-warm script
removes it before the demo.

### 4.3 The five agents

The four LLM agents share one `AsyncAnthropic` client created at startup and one helper in `llm.py`.
The helper calls `client.beta.messages.parse(...)` with:

- the agent's `output_format`;
- `output_config={"effort": ...}`;
- `betas=["server-side-fallback-2026-07-01"]` and `fallbacks="default"`.

The fallback settings come from Anthropic's guidance for Opus 5.5: if a safety classifier declines a request,
the API re-runs it on a fallback model inside the same call (for Sonnet 5.5 only the `"default"` form is accepted, which is the form used here). This was verified to work and costs no latency
(§2.2). Finance prompts are very unlikely to be declined. If `stop_reason == "refusal"` still comes back,
the stage fails with a readable message. The Writer uses `client.messages.stream(...)` instead.
The Opus 5.5 rules apply to every call:

- no `temperature` parameter (it is rejected);
- no `thinking={"type": "disabled"}` (it is rejected);
- set effort explicitly;
- read `parsed_output` only after checking `stop_reason`.

| Agent | Input | LLM | Output contract (all strings length-capped in the prompt) |
|---|---|---|---|
| **Financial Data Agent** | ticker | None: deterministic data agent | `FinancialProfile` |
| **Comps Agent** | company name, sector, industry, business summary (≤ 600 chars), Tavily snippets (≤ 1.5k tokens) | `COMPS_MODEL`, effort `low` | `PeerSelection` (3–5 tickers + ≤ 20-word rationale each) → code builds `CompsTable` |
| **Risk Agent** | risk-factor headings (≤ ~2k tokens) + filing metadata | `RISK_MODEL`, effort `low` | `RiskReport` (exactly 6 risks: title, category, severity 1–3, ≤ 30-word explanation, the source heading) |
| **Analyst Agent** | `FinancialProfile` (compact), `CompsTable`, `RiskReport`, `Scorecard`, news headlines | `ANALYST_MODEL`, effort `low` | `AnalystView` (signal, confidence, ≤ 60-word valuation summary, 3 thesis bullets, 3 counterpoints, ≤ 80-word signal reasoning) |
| **Writer Agent** | same compact JSON, minus the signal | `WRITER_MODEL` (**`claude-sonnet-5-5`**), effort `low`, streamed | Markdown with 4 fixed headings, ≤ 450 words total; parsed into `ReportNarrative` by heading |

Defaults: Comps, Risk and Analyst use `claude-opus-5-5`. The Writer uses **`claude-sonnet-5-5`**: Opus 5.5 always thinks before writing, so its streamed text first appeared after ~11 s, while Sonnet 5.5 started after ~1 s (§2.2). The Writer only rephrases numbers computed in code, so it doesn't need Opus-level reasoning. Sonnet 5.5 calls use effort `low` with thinking left at the default (adaptive); `thinking={"type": "disabled"}` is rejected on Sonnet 5.5 as well. The same `fallbacks="default"` setting applies on the Claude API.

Prompt caching is **not** a priority here. Each agent's system prompt is only ~300–800 tokens. Prompt caching
needs a minimum prefix of 512–4,096 tokens, depending on the model, and the per-ticker data changes every run. Keep system prompts
byte-stable anyway (no timestamps, `json.dumps(..., sort_keys=True)`), so caching can be switched on later
with a single top-level `cache_control` if prompts grow.

### 4.4 Sector-aware valuation (bank fix)

`scoring.py` selects the multiple set from yfinance `sector`:

- **Financial Services**: P/E (ttm, fwd), P/B, ROE, dividend yield, revenue growth. EV/EBITDA is omitted.
- **Real Estate**: P/E, P/B, dividend yield, EV/Revenue.
- **All other sectors**: P/E (ttm, fwd), EV/EBITDA, EV/Revenue, net margin, revenue growth, debt/equity.

The comps table shows:

- the target and each peer;
- the peer **median**;
- the target's premium or discount to the median.

Missing values show as `—`. They are left out of the median, never filled with zeros.

A peer is dropped if it fails validation:

- it is not `EQUITY`;
- it has no price;
- it is the target itself;
- it is a duplicate share class (for example GOOG/GOOGL).

If fewer than 3 valid peers remain, the Comps Agent is called once more with the rejected tickers listed.
After that, a static sector peer map (`peers_fallback.json`) is used.

### 4.5 Signal methodology (deterministic core, explained by Claude)

The scorecard has five factors. Each scores −1, 0 or +1, with thresholds kept in `config.py`:

1. Valuation vs. peer median (sector-appropriate primary multiple; ±15 % band)
2. Revenue growth vs. peer median
3. Profitability (net margin, or ROE for financials) vs. peer median
4. Analyst consensus upside (`targetMeanPrice / currentPrice − 1`; ±10 % band)
5. Momentum (price vs. 200-day average and position in the 52-week range)

A total of +2 or more gives BUY, −2 or less gives SELL, and anything else gives HOLD. The Analyst Agent sees the
factors and may move the signal by **at most one notch**, but must state why (for example, a severe 10-K risk).
Code enforces this rule.

Why this design:

- the same data always gives the same signal;
- the method is easy to explain in the demo;
- the LLM can't swing the result by mood, which matters because Opus 5.5 has no temperature control.

The UI and the report always show "Educational project — not investment advice."

### 4.6 Caching (SQLite, `backend/.cache/research.db`)

| Key | TTL | Reason |
|---|---|---|
| `quote:{ticker}` (`.info`) | 15 min | Prices move; fresh enough for a demo |
| `fin:{ticker}` (statements, history) | 24 h | Changes quarterly |
| `risk:{accession_no}` (extracted headings) | forever | A filing never changes; the accession number is resolved with the fast lookup |
| `riskreport:{accession_no}:{RISK_MODEL}` (Risk Agent output) | forever | Same filing + same model gives the same answer; saves one Claude call per run |
| `tavily:{query}` | 7 days | Saves credits; competitors rarely change |
| `peers:{ticker}:{COMPS_MODEL}` (Claude selection) | 7 days | Saves one Claude call |
| `report:{ticker}` | 1 h | Reopening a report is instant; the UI has a "Refresh" button |

On a warm cache the Comps and Risk Claude calls are skipped. Only the Analyst and the Writer run, so the critical
path drops to about **2 s + max(7 s, 10–14 s) ≈ 12–16 s**, with the signal at about 9 s.

Also call `edgar.set_cache_directory()` / `use_local_storage()` so filing HTML is reused.
`python -m equity_agent.warm AAPL NVDA JPM COST TSLA` fills the cache before the demo.

### 4.7 Resilience

- **Claude.**
  - `AsyncAnthropic(max_retries=2, timeout=60.0)`: the SDK retries 408/409/429/5xx and connection errors with backoff.
  - One `asyncio.Semaphore` (default 4) caps concurrent calls.
  - Errors are caught most-specific first: `NotFoundError` → bad model name in `.env`; `RateLimitError`; `APIStatusError`; `APIConnectionError`.
  - `message._request_id` is logged when a call fails.
- **Branches.** Every branch returns `Result | StageError`. A failed branch degrades the report instead of failing it (for example, "SEC filing unavailable: foreign issuer without 10-K/20-F"). Only a Stage 0 failure (unknown ticker) stops the run.
- **Ticker input.** Matches `^[A-Z][A-Z0-9._\-]{0,9}$` after upper-casing. `BRK.B` is converted to `BRK-B` for Yahoo.
  Native USD KASE routing and issuer enrichment are specified in `openspec/changes/add-kase-usd-market-data/`.
- **Secrets.** `ANTHROPIC_API_KEY` and `TAVILY_API_KEY` are never logged or sent to the frontend. `EDGAR_IDENTITY` is required at startup.

---

## 5. Data contracts

The source of truth is [`backend/src/equity_agent/models.py`](backend/src/equity_agent/models.py); this section
only summarises it. (An earlier copy of the classes here went stale, so it was removed.)

- **Data layer:** `Snapshot`, `Multiples`, `Quote`, `History` (4 fiscal years; 1 year of **daily** closes),
  `FinancialProfile`, `FilingRef`, `RiskHeadings`, and `Unavailable` for an expected absence. Every lookup returns
  `Fetched[T]` with the cache keys it was served from.
- **Claude output schemas** (kept simple: plain types, `Literal`, lists; limits are checked in code):
  - `PeerPicks`: the Comps Agent's pick call, tickers and names only;
  - `PeerRationales`: its explain call, one rationale per included peer, written from the peers' business
    summaries;
  - `RiskSelection`, `AnalystOutput`.
- **Assembled in code:** `CompsTable` (rows with each peer's summary, medians, target vs median, rationales,
  origin, exclusions), `PeerChoice` (the cached peer choice, built from and applied to a table), `Scorecard`.
- **Report:** `ResearchReport`, where each section is its result or a `StageError`, plus timings, per-call
  `LlmUsage`, cache hits, quality warnings and the disclaimer. Progress is streamed as `PipelineEvent`s.

Application-level checks after each Claude call:
- **Peers:** 3–5, distinct, valid tickers, not the target, then eligibility (equity, price, no second share class).
- **Rationales:** exactly one per included peer, at most 20 words.
- **Risks:** exactly 6, each quoting a real heading.
- **Signal:** at most one step from the preliminary signal, with a reason.

When a check fails, the call is repeated once with the broken rules listed. If it fails again, the stage is marked
as an error.

---

## 6. API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Models per agent, key presence (booleans only) |
| `GET` | `/api/research/stream?ticker=AAPL&refresh=false` | SSE stream of the run |
| `GET` | `/api/research/{ticker}` | Last cached `ResearchReport` (JSON) |

SSE events (`event:` name → `data:` JSON):

```text
stage      {"stage":"comps","status":"started"}
stage      {"stage":"comps","status":"done","ms":8410,"cached":false}
partial    {"key":"financials","value":{...}}        # UI renders the header and table immediately
partial    {"key":"comps","value":{...}}
partial    {"key":"analyst","value":{...}}            # signal card
narrative  {"delta":"Apple designs ..."}             # Writer text_stream
report     {...full ResearchReport...}
error      {"stage":"risk","message":"SEC filing unavailable"}   # non-fatal unless stage == "validate"
```

The frontend connects to FastAPI **directly** (`NEXT_PUBLIC_API_URL=http://localhost:8000`, CORS allows
`http://localhost:3000`), because the Next.js dev proxy can buffer SSE.

---

## 7. Project structure

```text
capstone/
├── IMPLEMENTATION_PLAN.md
├── README.md                       # setup, run, demo script, results for the 5 tickers, SDK deviation note
├── package.json                    # "dev:all": concurrently backend + frontend
├── backend/
│   ├── pyproject.toml              # uv; Python 3.13; anthropic, yfinance, curl-cffi, edgartools,
│   │                               # tavily-python, fastapi, uvicorn, pydantic, python-dotenv
│   ├── .env.example                # ANTHROPIC_API_KEY, TAVILY_API_KEY, EDGAR_IDENTITY, PYTHONUTF8=1,
│   │                               # COMPS_MODEL / RISK_MODEL / ANALYST_MODEL (default claude-opus-5-5), WRITER_MODEL (default claude-sonnet-5-5),
│   │                               # *_EFFORT (default low)
│   ├── equity_agent/
│   │   ├── config.py               # Settings dataclass, thresholds, TTLs, limits, per-agent model/effort
│   │   ├── llm.py                  # AsyncAnthropic client, semaphore, parse/stream helpers, usage + cost
│   │   ├── models.py               # Pydantic contracts (§5)
│   │   ├── cache.py                # SQLite TTL cache, @cached decorator
│   │   ├── data/
│   │   │   ├── market.py           # yfinance: snapshot, multiples, statements, history, batch peers
│   │   │   ├── sec.py              # edgartools: fast 10-K/20-F lookup, risk heading extraction
│   │   │   └── search.py           # Tavily: competitor search, news
│   │   ├── agents/
│   │   │   ├── base.py             # ClaudeAgent: name, system prompt, output_format, model, effort, validate()
│   │   │   ├── financial.py        # Financial Data Agent (deterministic)
│   │   │   ├── comps.py            # Comps Agent + peer validation + CompsTable builder
│   │   │   ├── risk.py             # Risk Agent
│   │   │   ├── analyst.py          # Analyst Agent + ±1 rule
│   │   │   ├── writer.py           # Writer Agent (streamed) + heading parser
│   │   │   └── prompts/*.md        # one system prompt per agent
│   │   ├── scoring.py              # sector-aware metric sets, medians, scorecard
│   │   ├── pipeline.py             # async orchestration, event emitter, timings
│   │   ├── api.py                  # FastAPI app + SSE
│   │   ├── cli.py                  # `uv run research AAPL [--json] [--no-cache]`
│   │   ├── warm.py                 # pre-warm cache for demo tickers
│   │   └── peers_fallback.json
│   └── tests/
│       ├── fixtures/{AAPL,NVDA,JPM,COST,TSLA}/   # recorded info/statements/headings/tavily JSON + Claude outputs
│       ├── fakes.py                              # FakeClaude: returns recorded parsed outputs / text streams
│       ├── test_market.py  test_sec.py  test_scoring.py  test_comps.py  test_agents.py
│       ├── test_pipeline.py                      # whole run on fixtures with FakeClaude
│       └── test_live.py                          # opt-in: RUN_LIVE_TESTS=1 (spends a few cents)
└── frontend/
    ├── package.json                # next 16, react 19, tailwind 4, recharts, react-markdown
    ├── .env.local.example          # NEXT_PUBLIC_API_URL=http://localhost:8000
    └── src/
        ├── app/page.tsx            # ticker input + quick-pick chips (AAPL, NVDA, JPM, COST, TSLA)
        ├── app/report/[ticker]/page.tsx
        ├── lib/api.ts  lib/types.ts  lib/useResearchStream.ts   # EventSource hook
        └── components/
            ├── AgentProgress.tsx   # 5 agent cards: pending → running → done (ms, cached, model)
            ├── PriceHeader.tsx     # price, change, market cap, 52-week range bar
            ├── KeyFinancials.tsx   # metric grid + revenue/EBITDA bars
            ├── PriceChart.tsx      # 1y line (Recharts)
            ├── CompsTable.tsx      # target highlighted, median row, ▲▼ vs median, peer rationale, sources
            ├── ValuationChart.tsx  # primary multiple vs peers (bar)
            ├── RiskList.tsx        # severity chips, category, link to filing
            ├── SignalCard.tsx      # BUY/HOLD/SELL badge, confidence, scorecard factors, reasoning
            └── Narrative.tsx       # streamed markdown + disclaimer
```

---

## 8. Implementation milestones (solo)

Each milestone ends with something runnable and tested. Build the backend first, all the way to a working CLI,
so every later step has real data to show.

**M0 — Setup (½ day)**
- Create the projects: `uv init backend` and add the dependencies; run `create-next-app frontend --ts --tailwind --app`.
- Add the `.env.example` files and `/api/health`.
- Check that `curl_cffi` imports, that a 1-line Claude call works (check `stop_reason` and log usage), that the Tavily key works and that `EDGAR_IDENTITY` is set.

**M1 — Data layer, no LLM (1 day)**
- Build `market.py`, `sec.py` (with `trigger_full_load=False` and heading extraction), `search.py` and `cache.py`.
- Record fixtures for the 5 tickers.
- Tests:
  - an invalid ticker is rejected;
  - JPM has no EV/EBITDA;
  - AAPL has 20–80 heading lines;
  - a cache hit makes no network call.

**M2 — Scoring and comps math (½ day)**
- Build `scoring.py`: metric sets, medians that ignore `None`, premium/discount and scorecard thresholds.
- Use pure functions with table-driven tests.

**M3 — Claude agents and pipeline, CLI (1½ days)**
- Build `llm.py`: client, semaphore, `parse()` with effort and fallbacks, `stream()`, usage and cost tracking.
- Build the four Claude agents with their prompts, `pipeline.py` with `asyncio.gather` and the Analyst ∥ Writer step, and `cli.py`.
- Tests use `FakeClaude` with recorded outputs. They cover:
  - stage order and parallelism;
  - degraded branches;
  - the ±1 rule;
  - peer validation and re-asking when there are too few peers;
  - refusal handling.
- Do one live CLI run for AAPL and record the timings and cost.

**M4 — API + SSE (½ day)**
- `api.py` streams pipeline events, and the report cache has its own endpoint.
- Test with `curl -N`.

**M5 — Frontend (2 days)**
- Build the streaming hook, progress cards, header, financials, comps table, charts, risks, signal card and narrative.
- Add loading skeletons, error states and a responsive layout.
- Use the `frontend-design` skill for visual polish.

**M6 — Evaluation, performance, demo hardening (1 day)**
- Run the 5-ticker test matrix (§9) and record the timings, cost and outputs in `README.md`.
- Tune prompts, length caps and thresholds.
- Try effort `medium` on the Analyst only if the signals look shallow.
- Confirm the Writer's time to first text is about 1 s in the UI.
- Add `warm.py` and an offline demo mode: `DEMO_OFFLINE=1` serves fixtures and cached reports in case Wi-Fi fails.
- Rehearse the demo.

Total: about **7 working days**. The `models.py` ↔ `lib/types.ts` contract is defined at the end of M1. Keep it
in sync by generating `types.ts` from the FastAPI OpenAPI schema (`openapi-typescript`) rather than writing it by hand.

---

## 9. Testing and acceptance

### 9.1 Test matrix

| Ticker | What it exercises | Pass criteria |
|---|---|---|
| **AAPL** | Large-cap baseline | ≥ 3 valid peers (e.g. MSFT, GOOGL, DELL; OTC listings such as SSNLF kept only if yfinance returns usable multiples), full multiples, 10-K risks |
| **NVDA** | High growth, very high multiples | Growth factor +1 while valuation factor is −1; reasoning mentions this tension |
| **JPM** | Financials | `metric_set == "financials"`, no EV/EBITDA, bank peers (BAC, C, WFC, GS/MS); slowest 10-K (cold ~17 s parse, warm 0) |
| **COST** | Stable retail | Peers WMT, TGT, BJ, DG/AMZN; risk section non-empty |
| **TSLA** (suggested 5th) | Auto/tech ambiguity, volatile | Peer choice is sensible (GM, F, RIVN; BYD ADR filtered if no valid data) |
| Edge: `ZZZZQX`, `brk.b`, `TSM` (20-F filer) | Validation and fallbacks | Clear error / `BRK-B` resolves / risks from 20-F or graceful "unavailable" |

### 9.2 Automated tests

- **Offline** (the default `uv run pytest`): uses fixtures and `FakeClaude`. No network, no keys, no cost.
- **Type checks:** `uv run pyright` in standard mode.
- **Live** (opt-in with `RUN_LIVE_TESTS=1`, about $0.15 per run): one AAPL end-to-end run. It checks for:
  - at least 3 comps rows with at least 2 multiples each;
  - a valid signal;
  - a non-empty narrative;
  - total time under 40 s.

### 9.3 Performance budget (logged in `timings_ms` of every report)

| Milestone in the UI | Cold cache | Warm cache (Comps/Risk outputs cached) |
|---|---|---|
| Price header | ≤ 3 s | ≤ 0.5 s |
| Financials + comps table + risks | ≤ 12 s | ≤ 2 s |
| Signal card (Analyst) | ≤ 20 s | ≤ 10 s |
| Narrative complete (Writer) | ≤ 25 s | ≤ 16 s |
| Same ticker reopened within 1 h | instant | instant |

If the Writer is the bottleneck after M6, the levers in order are:

1. a lower word limit;
2. `WRITER_MODEL=claude-haiku-4-5` (measured 6.3 s on the capped analyst prompt);
3. dropping the separate Writer prose in favour of the Analyst's text.

---

## 10. Demo script (≈ 5 minutes)

1. Before the demo, run `uv run python -m equity_agent.warm AAPL NVDA JPM COST TSLA`, then `npm run start:all` (never
   `dev:all`: it reloads the API on save and compiles each page on first visit). Wait for "Application startup complete".
   The full runbook, including the offline fallback, is in the README.
2. **AAPL**: show the five agent cards lighting up, the tables appearing before the narrative, and the signal card with the scorecard and the agent's reasoning.
3. **JPM**: point out the sector-aware table (P/B and ROE instead of EV/EBITDA).
4. **NVDA** vs **COST**: the same pipeline gives different signal reasoning (growth vs. valuation).
5. A ticker you haven't cached (cold run, about 21–25 s, tables at about 11 s) to prove it's live.
6. Show `timings_ms`, `llm_usage` (tokens and cost per agent) and the cache hits to explain the performance design.

---

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Claude latency higher than planned | Length caps, effort `low`, Analyst ∥ Writer, per-agent model switch in `.env` (§9.3 levers), report cache |
| Rate limit or outage during the demo | SDK retries; pre-warmed cached reports; `DEMO_OFFLINE=1` |
| Unexpected API spend | Usage and cost logged per agent and per report; cached Comps/Risk outputs; live tests opt-in only; set a monthly spend limit in the Claude Console |
| Wrong Opus 5.5 parameters (400 errors) | `llm.py` is the only place that builds requests: no `temperature`, no disabled thinking, effort always explicit; one live smoke test in M0 |
| Yahoo throttling / field changes | `curl_cffi`, caching, threaded batch, `None`-tolerant parsing, fixture tests |
| Claude proposes invalid or foreign peers | Validate via yfinance, re-ask once, static fallback map |
| Huge 10-K (JPM) parse time | Fast lookup flag, heading extraction cached per accession number, pre-warm; optionally parse in a `ProcessPoolExecutor` so it doesn't hold the GIL |
| Hallucinated numbers in prose | Writer receives computed numbers only; prompt forbids new figures; UI tables come from data, not from text |
| Signal seen as financial advice | Disclaimer in UI and report; deterministic, documented methodology |
| Deviation from the brief's suggested SDK | One README paragraph explaining the choice (§3.1); the Researcher → Analyst → Writer pattern and the five agents are kept |
| Windows MAX_PATH / encoding | Keep the project path short; `PYTHONUTF8=1` |

---

## 12. Open decisions

1. ~~Writer model~~ **Decided 2026-10-01:** the Writer uses `claude-sonnet-5-5` (first streamed text in ~1 s vs ~11 s on Opus 5.5). The other agents stay on `claude-opus-5-5`.
2. **5th ticker.** TSLA is suggested (named in the brief, volatile, ambiguous peer set). TSM would also test the 20-F path.
3. **Analyst effort.** Keep `low` (7 s) unless the M6 review finds the reasoning shallow; `medium` measured 29 s with uncapped output.

## Sources

- Claude models, pricing and API behaviour: Anthropic's API reference bundled with Claude Code (model table cached 2026-09-25); [Anthropic pricing](https://www.anthropic.com/pricing)
- [Tavily API credits](https://docs.tavily.com/documentation/api-credits)
- [Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) (for the comparison only)
- [OpenAI cookbook: parallel agents with the Agents SDK](https://developers.openai.com/cookbook/examples/agents_sdk/parallel_agents) (alternative B)
- [Next.js blog](https://nextjs.org/blog) (16.3 current stable, Aug 2026)
