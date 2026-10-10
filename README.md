# Autonomous Equity Research Agent

Type a stock ticker and get a research report: company overview, key financials, a peer comps table with
valuation multiples, 10-K risk factors, and a BUY / HOLD / SELL signal with reasoning. Five agents do the work:
Financial Data, Comps, Risk, Analyst and Writer. They run on Claude (Anthropic SDK) using data from Yahoo Finance,
KASE, SEC EDGAR and Tavily web search. The application runs locally and contacts remote data, model and search providers.

> Educational project - not investment advice.

- Design, measured benchmarks and decisions: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)
- Implementation specs (OpenSpec, one change per milestone): [openspec/changes/](openspec/changes/)

## Status

| Milestone (OpenSpec change) | State |
|---|---|
| `setup-project-foundation`: scaffolding, settings, health endpoint, smoke check, demo start command | done |
| `add-market-data-layer`: Yahoo, SEC EDGAR and Tavily behind a SQLite cache; warm 10-K parser process | done |
| `add-valuation-scoring`: sector-aware comps table, five-factor scorecard, preliminary signal | done |
| `add-research-agents`: Claude gateway, five agents, concurrent pipeline, `research` CLI | done |
| `add-ragas-evaluation`: Ragas faithfulness and answer relevancy, Claude Haiku 4.5 judge | done (baseline below) |
| `consolidate-duplicated-logic`: one failure vocabulary, report runner, formatter and cache-hit convention (from the redundancy review) | done |
| `add-research-api`: streamed research over Server-Sent Events, cached reports, warm start, generated TypeScript types | done |
| `add-research-web-ui`: the report page, sections appearing as their agents finish | done |
| `add-demo-readiness`: cache warm-up, offline demo mode, acceptance evaluation of the test tickers, demo runbook | done |
| `add-kase-usd-market-data`: native USD quotes, explicit issuer enrichment, reporting currencies and provenance | implemented; live availability remains provider-dependent |

## Native KASE USD research

Enter `FRHC_KZ`, `HSBKd`, `KSPId`, `KZAPd`, or a supported KASE Global symbol such as `AAPL_KZ`.
Ticker validation accepts underscores, trims whitespace and uppercases inputs (up to ten characters).
The official depositary-receipt casing is retained beside the quote. `CORE_KZ` is recognized but currently
has no quoted price; it returns **quote unavailable**. KZT ordinary-share coverage is unchanged.

The production router fetches KASE's public website JSON with a ten-second timeout. Only a positive finite
`price` is used. A missing price, changed instrument identity, unsupported currency/type, malformed response
or outage stays visible. Quotes never fall back to a foreign exchange, `close_price`, bids or offers.
The website API is undocumented, so its availability and schema can change.

| Native research input | Yahoo issuer enrichment | Shares per native / source unit | SEC input |
|---|---|---|---|
| `FRHC_KZ` | `FRHC` | 1 / 1 | `FRHC` |
| `KSPID` | `KSPI` | 1 / 1 | `KSPI` |
| `HSBKD` | `HSBK.IL` | 40 / 40 | unavailable |
| `KZAPD` | `KAP.IL` | 1 / 1 | unavailable |
| `AAPL_KZ` | `AAPL` | 1 / 1 | `AAPL` |
| `NVDA_KZ` | `NVDA` | 1 / 1 | `NVDA` |
| `JPM_KZ` | `JPM` | 1 / 1 | `JPM` |
| `CORE_KZ` | none | no enrichment | unavailable |

Mappings include expected issuer identities, ISINs and verified share units. Private London identifiers retain
`.IL`; aliases are never inferred by removing suffixes. Financial histories remain in their reporting currency,
including KZT accounts for a USD-traded receipt. Unknown reporting currency suppresses monetary history with a
diagnostic. Old saved reports remain readable; monetary history without a known currency is hidden until refreshed.

For verified USD accounts, P/E, forward P/E and P/B use `native price / (alias price × native/source shares)`;
dividend yield uses the inverse adjustment. Verified USD capitalization uses the same price ratio. USD analyst
targets use the shares-per-unit conversion and are labelled cross-listing estimates. No FX conversion is performed.
Non-USD accounts leave price-sensitive valuation ratios unavailable; EV-based ratios are unavailable for all native
KASE targets. Native annual trading history and 52-week ranges are unavailable, with neutral momentum. Alias
prices and histories cannot become KASE quotes or charts. Enrichment failures preserve the native quote.

Offline regressions: `uv run --directory backend pytest tests/test_kase_adapter.py tests/test_kase_cases.py`.
The opt-in USD matrix runs five native quote probes, two US-listing reports and a native `FRHC_KZ` report:

```powershell
cd backend
$env:RUN_LIVE_TESTS = '1'
uv run pytest -m live tests/test_kase_usd_live.py -q -s
```

Reports use Claude/Tavily credits. Each run creates a new timestamped `docs/kase-usd-*` directory containing
quotes, full reports, checks, cost and diagnostics. A missing live price fails quote availability; its controlled
handling is tested separately offline. Earlier execution evidence is preserved.

## Setup

### Prerequisites

- Windows 11, macOS or Linux; [uv](https://docs.astral.sh/uv/) ≥ 0.10; Node.js ≥ 20 with npm
- An [Anthropic API key](https://platform.claude.com/settings/keys) (paid, about $0.12–0.15 per report)
- A [Tavily API key](https://app.tavily.com) (the free plan's 1,000 credits a month cover about 500 reports)
- A contact identity for SEC EDGAR (`Your Name your.email@example.com`). SEC requires one on every request.

**Keep the project path short.** On Windows a deeply nested folder pushes `backend/.venv` past the 260-character path
limit. The `curl_cffi` DLL then fails to load, and yfinance silently falls back to a client that Yahoo rate-limits.
Running from `C:\Users\<you>\Documents\Sources\...\capstone` works. The smoke check below detects the problem.

**PowerShell** may block the venv's scripts. Allow them for the current session:

```powershell
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process
```

### Install

From the repository root:

```bash
npm install
npm --prefix frontend install
uv sync --directory backend
```

### Configure

```bash
cp backend/.env.example backend/.env
cp frontend/.env.local.example frontend/.env.local
```

Fill in `ANTHROPIC_API_KEY`, `TAVILY_API_KEY` and `EDGAR_IDENTITY` in `backend/.env`. The other settings have
working defaults:

- the Comps, Risk and Analyst agents use `claude-opus-5-5`;
- the streamed Writer uses `claude-sonnet-5-5`;
- every agent uses effort `low`.

Change any agent's model or effort with `<AGENT>_MODEL` / `<AGENT>_EFFORT`. The server refuses to start if a required
setting is missing or an effort value is invalid, and the error names the setting. Key values never appear in logs,
errors or API responses.

### Check the external services

```bash
uv run --directory backend python -m equity_agent.smoke
```

Expected output: five `PASS` lines (curl_cffi, Claude, Tavily, SEC EDGAR, Yahoo Finance). The Claude check also
confirms that every configured model name exists. It costs a fraction of a cent and 1 Tavily credit.

### Run

```bash
npm run dev:all
```

This starts the API on <http://localhost:8000> (health: <http://localhost:8000/api/health>) and the web app on
<http://localhost:3000>. No Docker or hosting is needed. Stop both servers with Ctrl+C.

`dev:all` reloads the API whenever a file in `backend/src` is saved, and compiles each web page on its first visit.
For a demo, or to measure performance, use the demo mode instead:

```bash
npm run start:all
```

It builds the frontend first, then serves the built pages, and runs the API without auto-reload. Wait for the
`Application startup complete` line before opening the app.

**Port 8000 taken by another program:** the API then logs `[Errno 10048] error while attempting to bind`. Find
the owner:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen | ForEach-Object { Get-Process -Id $_.OwningProcess }
```

If it is `wslrelay.exe`, a service inside WSL is publishing port 8000.

**Port 8000 still in use after a crash (Windows):** if the terminal was killed instead of stopped with Ctrl+C,
uvicorn's reload worker can outlive its parent and keep the port. Find it by its parent process and stop it:

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object CommandLine -like '*multiprocessing.spawn*' | Select-Object ProcessId, ParentProcessId, CommandLine
```

### Using the web app

Open <http://localhost:3000>, type a ticker (or pick one of the five test tickers) and press Enter. The report page
shows one card per pipeline step and fills in each section as its agent finishes: price header, key financials and
price chart, the comps table and valuation chart, the rating (the scorecard's preliminary signal first, then the
analyst's review), risks, news and the streamed research note. Hover or focus a peer in the comps table for why it
was chosen. **Refresh** starts a new run that bypasses the cached report; **Diagnostics** at the bottom shows stage
timings, every model call with its tokens and cost, cache hits and quality warnings.

On 2026-10-04 the comps table appeared 1.6–2.5 s after opening a report whose peers were cached, and 6.1 s into a
refreshed TSLA run, before the first narrative text in every run. The refreshed TSLA report finished at 13.4 s for
$0.075.

### Research from the command line

```bash
cd backend
uv run research AAPL            # readable report with stage timings and estimated cost
uv run research JPM --json      # one JSON document (the ResearchReport schema)
uv run research NVDA --refresh  # bypass cached reports, peers, quotes and searches
```

A report is cached for an hour, the chosen peers for 7 days and the Risk Agent's selection for as long as the filing
is current, so repeat runs are fast and cheap. Two more manual checks print the intermediate layers:
`uv run python -m equity_agent.data.inspect AAPL` (data layer) and
`uv run python -m equity_agent.scoring AAPL MSFT GOOGL DELL` (comps table and scorecard).

### Research API

With the API running (`npm run start:backend`, or either `:all` script):

```bash
curl -N "http://localhost:8000/api/research/stream?ticker=AAPL"
curl "http://localhost:8000/api/research/AAPL"
```

| Endpoint | Returns |
|---|---|
| `GET /api/research/stream?ticker=&refresh=` | Server-Sent Events for one run; a second request for the same ticker joins the run in progress |
| `GET /api/research/{ticker}` | the cached report (1 hour) as JSON; 404 when there is none, 400 for an invalid ticker |
| `GET /api/health` | models, effort and which keys are set (never their values) |

Each event is `event: <name>` plus `data: <json>`:

| Event | Payload | Notes |
|---|---|---|
| `stage` | `{"stage": "comps", "status": "started"}`, then `{"stage": "comps", "status": "done", "ms": 6774, "cached": false}` | `status` can also be `failed` |
| `partial` | `{"key": "comps", "value": {...}}` | keys: `snapshot`, `financials`, `comps`, `risks`, `news`, `scorecard`, `analyst`. A later partial with the same key replaces the earlier one: comps arrive first without `peer_rationales`, then again with them |
| `narrative` | `{"delta": "## Company overview

Apple..."}` | the Writer's text, as it streams |
| `error` | `{"stage": "risk", "message": "SEC filing unavailable", "terminal": false}` | `terminal: true` (for example `ticker not found` at `validate`) ends the stream |
| `report` | the whole `ResearchReport`, plus `"from_cache": true/false` | always the last event of a successful run |

A refreshed COST run on 2026-10-04 delivered the comps table to the client at 7.2 s, the first narrative text at
8.2 s, the comps rationales at 11.3 s and the report at 15.2 s. The stream is never compressed, because compression
would hold events back. A client that disconnects only stops its own stream; the run finishes and caches its report.

The API's start-up loads the data libraries, starts and warms the filing-parser worker and opens the Claude
connection before it accepts requests (about 20 s), so the first report pays for none of it. Stopping the API with
Ctrl+C also stops the worker.

## Demo runbook

**The day before (or an hour before):**

1. Refresh the offline recording and check the test tickers in one go (about $0.70 of Claude, 14 Tavily credits,
   4 minutes). It writes `backend/eval/acceptance-cold.md` and the recording in `backend/demo/`:

   ```bash
   cd backend
   uv run python -m equity_agent.evaluate --record
   ```

   Every row should say `pass`. A failure names the criterion that failed.

**Right before the demo:**

2. Warm the caches (a few cents: the Comps and Risk agents only, and nothing for tickers that are still warm), so
   each demo report only runs the Analyst and Writer:

   ```bash
   cd backend
   uv run python -m equity_agent.warm AAPL NVDA JPM COST TSLA
   ```

3. Start the demo build from the repository root. Never use `dev:all` for a demo: it reloads the API on every save
   and compiles each page on its first visit.

   ```bash
   npm run start:all
   ```

   Wait for `Application startup complete` (about 20 s: the data libraries load, the filing parser starts and the
   Claude connection opens), then open <http://localhost:3000>.

**The demo (about 5 minutes):**

4. **AAPL**: the seven agent cards light up, the price header, financials and comps table arrive before the
   research note, and the rating shows the scorecard's preliminary signal before the analyst confirms or changes it.
   Hover a peer for why it was chosen.
5. **JPM**: the sector-aware comps table uses P/B and ROE instead of EV/EBITDA.
6. **NVDA** then **COST**: the same pipeline reasons differently about growth versus valuation.
7. A ticker you haven't warmed (for example `MSFT`): a cold run with peer rationales arriving after the table.
   Press **Refresh** on any report to force one.
8. Open **Diagnostics** at the bottom: stage timings, each model call with its tokens and cost, and cache hits.

**If the network or a service fails:** stop the servers (Ctrl+C), then restart in offline mode. Reports for the
recorded tickers (AAPL, NVDA, JPM, COST, TSLA, BRK-B, TSM) replay the recording through the same pipeline and
streaming, with an **Offline demo** badge in the header and no network calls. Other tickers say "not available
offline".

```powershell
$env:DEMO_OFFLINE = "1"; npm run start:all
```

```bash
DEMO_OFFLINE=1 npm run start:all
```

`DEMO_REPLAY_SPEED` (default 0.4) sets how long the replayed model calls take, as a share of their recorded time.

### Acceptance results (2026-10-04)

`uv run python -m equity_agent.evaluate` checks AAPL, NVDA, JPM, COST and TSLA (price and key financials, at least 3
peers with 2+ valuation multiples, a reviewed signal with reasoning, a risk section or a reason, the disclaimer;
for JPM also the financials metric set without EV/EBITDA) and three edge cases (`ZZZZQX` gives "ticker not found",
`BRK.B` resolves to `BRK-B`, `TSM` gets its risks from the 20-F). Every agent runs live in every report. After the
warm-up, as in a demo:

| Ticker | Result | Signal | Peers | Comps ready | Total | LLM calls | Cost | Budget |
|---|---|---|---|---|---|---|---|---|
| AAPL | pass | HOLD | 5 | 3.0 s | 16.9 s | 5 | $0.099 | within |
| NVDA | pass | BUY | 5 | 3.4 s | 15.9 s | 5 | $0.101 | within |
| JPM | pass | BUY | 5 | 3.0 s | 14.7 s | 5 | $0.101 | within |
| COST | pass | HOLD | 5 | 4.7 s | 14.8 s | 5 | $0.099 | within |
| TSLA | pass | HOLD | 5 | 2.0 s | 15.5 s | 5 | $0.101 | within |
| ZZZZQX | pass | — | — | — | — | 0 | $0.000 | — |
| BRK.B | pass | HOLD | 5 | 3.1 s | 15.5 s | 5 | $0.092 | within |
| TSM | pass | BUY | 5 | 3.3 s | 17.2 s | 5 | $0.110 | within |
| **Total** | 8/8 pass | | | | | 35 | $0.703 | 0 over |

Budget: comps table ≤ 12 s and report ≤ 30 s. The cold run (`--record`, nothing cached) also passed 8/8 with every
comps table under 9 s, but three reports went over 30 s: JPM 30.0 s, TSM 36.8 s and BRK-B 44.0 s. In each, the
risk branch (first download and parse of the annual filing, then the Risk agent: 22–36 s) held up the Analyst and
Writer. That cost is paid once per filing, which is what the warm-up is for. Full tables:
`backend/eval/acceptance.md` and `backend/eval/acceptance-cold.md`.

## How it works

```text
ticker -> validate (Yahoo quote: equity with a price)
       -> concurrently: Financial Data (no LLM) | Comps (Tavily -> Claude picks peers -> comps table in code)
                        | Risk (10-K headings -> Claude picks 6) | News (Tavily)
       -> scorecard in code: valuation, growth, profitability, analyst upside, momentum -> preliminary signal
       -> concurrently: Analyst (Claude may move the signal one step, with a reason) | Writer (Claude streams prose)
       -> ResearchReport (cached 1 h)
```

- **Claude never does arithmetic.** Multiples, medians, premiums and the scorecard are Python. Agents receive
  compact JSON with numbers already formatted, and the Writer's prose is checked for numbers that are not in its
  input (reported as quality warnings).
- **One structured call per agent**, validated in code (peer count and eligibility, exactly 6 risks quoting real
  headings, the one-step signal rule, word limits), with at most one re-ask listing the broken rules. Comps fall back
  to a static sector peer list if Claude's picks still don't validate.
- **Models:** Opus 5.5 for Comps, Risk and Analyst; Sonnet 5.5 for the streamed Writer (first text in about 1 s).
  Effort `low` everywhere, server-side refusal fallback on, timeouts of 30 s per structured attempt (60 s with
  retries) and 60/90 s for the stream.
- **Degrades, never crashes:** a failed risk, news, comps or writer branch becomes an error entry in its section;
  a failed Analyst leaves the preliminary signal, marked as not reviewed. Only an unknown ticker stops a run.

**Deviation from the brief:** the brief names the OpenAI Agents SDK. This project calls Claude through the
official Anthropic SDK directly, and the agents are plain Python classes orchestrated in code. There is no tool loop
or handoff for an agent framework to manage, and the native SDK gives first-class effort, refusal and usage fields.
The brief's five named agents and its Researcher -> Analyst -> Writer flow are kept. Reasoning and measurements:
[IMPLEMENTATION_PLAN.md §3.1](IMPLEMENTATION_PLAN.md#31-agent-layer-native-anthropic-sdk-instead-of-the-openai-agents-sdk).

### Measured on the five test tickers (2026-10-03, every agent running, data cache warm, two-call Comps)

| Ticker | Peers | Risks | Signal | Comps ready | Signal ready | Total | Cost |
|---|---|---|---|---|---|---|---|
| AAPL | MSFT, GOOGL, DELL, HPQ, SONY | 6 | HOLD | 5.3 s | 17.2 s | 17.2 s | $0.100 |
| NVDA | AMD, AVGO, INTC, MRVL, QCOM | 6 | BUY | 4.4 s | 15.3 s | 15.3 s | $0.103 |
| JPM | BAC, C, WFC, GS, MS (bank metrics, no EV/EBITDA) | 6 | BUY | 4.3 s | 13.7 s | 14.6 s | $0.101 |
| COST | WMT, BJ, PSMT, TGT, KR | 6 | HOLD | 4.2 s | 13.4 s | 14.0 s | $0.099 |
| TSLA | GM, F, TM, RIVN, LI | 6 | HOLD | 3.8 s | 14.2 s | 15.7 s | $0.099 |

All within the budget (comps ≤ 12 s, total ≤ 30 s). The Analyst confirmed the scorecard's preliminary signal in all
five cases.

## Evaluation (Ragas)

The agents' text is scored with [Ragas](https://docs.ragas.io) as in the `llm-as-a-judge` project:

- **faithfulness**: the share of the text's statements that are supported by the data the agent was given;
- **answer relevancy**: whether the text addresses its task.

The judge is Claude Haiku 4.5, a different model family from the generators. Each sample's "context" is the exact
JSON input that agent received.

```bash
cd backend
uv run --group eval python eval/run_ragas.py           # 5 fresh reports + scoring, about $1.10
uv run --group eval python eval/run_ragas.py --reuse   # re-score the saved reports, about $0.70
```

The `eval` dependency group (Ragas, sentence-transformers with PyTorch, LangChain 0.3) is installed only by
`--group eval`; the app and its tests don't need it. Results: `backend/eval/results/ragas_summary.md`.

Latest run (2026-10-03, snapshot `2026-10-03-early-comps`). Faithfulness rose from 0.814 at the baseline through
three changes; the history and caveats are in the dated note linked below.

| Agent | Faithfulness | Answer relevancy |
|---|---|---|
| Writer | 0.974 | 0.399 |
| Analyst | 0.851 | 0.570 |
| Risk | 0.991 | — |
| Comps | 0.868 | — |
| All | 0.944 | 0.433 |

**How to read it:**
- **Writer:** grounded; no section introduced a figure that was not in its input.
- **Analyst:** loses points mostly for judgements, which are its job.
- **Risk:** now restates only what the filing headings say.
- **Comps:** rationales are now written from the peers' own business summaries by a second short call that runs in
  the background after the table is shown (+$0.02 per report, no added wait).
- **Answer relevancy:** low for instruction-style tasks by construction, so use it to compare runs.
- **Comparing runs:** `uv run python eval/compare.py 2026-10-03-baseline 2026-10-03-early-comps`. Add
  `--snapshot NAME` to an evaluation run to keep its scores under `backend/eval/runs/NAME/`.

Details, caveats and next levers: [docs/2026-10-03-ragas-baseline.md](docs/2026-10-03-ragas-baseline.md).

## Development

```bash
cd backend
uv run pytest        # offline tests, no keys or network needed
uv run pyright       # type check (standard mode)
RUN_LIVE_TESTS=1 uv run pytest -m live   # opt-in tests against real APIs (spend credits)
```

```bash
cd frontend
npm test             # Vitest: formatting, the event reducer and components, over real pipeline event fixtures
npm run build
npm run lint
```

The frontend's test fixtures are event sequences from the real pipeline (recorded data, fake Claude). Regenerate
them after changing an event payload: `cd backend && uv run python scripts/export_ui_fixtures.py`.

After changing a model in `backend/src/equity_agent/models.py`, regenerate the frontend's types from the API schema
(no server or keys needed): `npm run gen:types` writes `frontend/src/lib/types.ts`.

### Redundancy measures

`uv run python scripts/redundancy_counts.py` (in `backend/`) prints the measures from the
`consolidate-duplicated-logic` change. Before and after that change (2026-10-03):

| Measure | Before | After |
|---|---|---|
| `except` blocks in `pipeline.py` | 15 | 6 |
| places recording cache hits / usage in `pipeline.py` | 8 / 10 | 1 / 1 (one helper each) |
| error messages parsed with `split(":")` | 2 | 0 |
| hand-rolled ticker cleaning | 4 | 0 |
| copies of "run a report and get the result" | 3 | 1 (`run_report`) |
| number formatters | 2 + 2 truncation copies | 1 module (`formatting.py`) |

A characterisation test (`tests/test_characterisation.py`) pins every agent's input and each fixture report, so a
refactor that changes what the models receive fails the suite.

### Project layout

```text
backend/            Python 3.13, uv, FastAPI (src/equity_agent/)
frontend/           Next.js 16, TypeScript, Tailwind CSS v4
backend/demo/       offline demo recording (provider data + agent answers), written by `evaluate --record`
docs/               dated evaluation notes
openspec/           specs and change proposals (OpenSpec CLI: openspec list, openspec validate --all --strict)
IMPLEMENTATION_PLAN.md
```
