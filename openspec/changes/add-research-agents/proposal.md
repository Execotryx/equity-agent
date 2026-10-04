# Proposal

## Why

With data and deterministic scoring in place, the product still needs the parts that require judgement:

- choosing sensible peers;
- condensing dozens of 10-K risk headings into the few that matter;
- explaining or adjusting the signal;
- writing a readable report.

It also needs an orchestrator that runs everything fast enough for a live demo. This change adds four Claude-backed
agents and the parallel pipeline that produces a complete `ResearchReport`, usable from a CLI (IMPLEMENTATION_PLAN.md
§3.1, §4.1–4.3, milestone M3).

## What Changes

- One shared, guarded way to call Claude:
  - typed structured outputs;
  - explicit effort per agent;
  - refusal detection with server-side fallback;
  - bounded concurrency and retries;
  - per-call usage and cost accounting.
- **Comps Agent:** picks 3–5 US-listed peers from web-search snippets and company context. It is re-asked once when
  too few peers are eligible, then falls back to a static sector peer map.
- **Risk Agent:** selects and categorises exactly 6 risks from the filing's risk headings.
- **Analyst Agent:** confirms or moves the preliminary signal by at most one notch, with a stated reason, a thesis
  and counterpoints.
- **Writer Agent:** streams four narrative sections. It must not introduce numbers that are not in its input.
- **Financial Data Agent:** deterministic, no LLM.
- **Pipeline:**
  - validation first;
  - the Comps, Risk, Financial and News branches run concurrently;
  - scoring;
  - the Analyst and Writer run concurrently;
  - progress events, timings, degraded-branch handling and caching of agent outputs and whole reports.
- A CLI: `uv run research <TICKER> [--json] [--refresh]`.
- **Deviation from the brief (documented in the README):** agents use the Anthropic SDK directly instead of the
  OpenAI Agents SDK. The brief's Researcher → Analyst → Writer pattern and the five named agents are kept.

## Capabilities

### New Capabilities

- `llm-gateway`: how the service calls Claude (structured output, effort, refusals, retries, concurrency,
  usage/cost reporting, output validation with one re-ask).
- `research-agents`: the behaviour contract of the Comps, Risk, Analyst, Writer and Financial Data agents.
- `research-pipeline`: orchestration, ordering and concurrency, degradation, progress events, timings, report
  assembly and caching, and the CLI.

### Modified Capabilities

(none)

## Impact

- New modules: `llm.py`, `agents/` (with `prompts/*.md`), `pipeline.py`, `cli.py`, `peers_fallback.json`.
- Spends Anthropic API credit: about $0.10–0.15 per uncached report (Opus 5.5 for three agents, Sonnet 5.5 for the
  Writer). Live tests are opt-in only.
- Depends on `add-market-data-layer` and `add-valuation-scoring`.
