# Proposal

## Why

The agents turn computed data into prose: the Writer's four sections, the Analyst's thesis and reasoning, the Risk
Agent's explanations and the Comps Agent's peer rationales. The structural checks in `add-research-agents` (counts,
word limits, the ±1 signal rule, a regex for numbers) cannot tell whether a sentence is actually supported by the data
the agent was given. An unsupported claim in a research report is the failure that matters most.

As in the previous cohort project (`llm-as-a-judge`), this change measures that with Ragas: **faithfulness** (share of
claims supported by the agent's input) and **answer relevancy** (whether the text addresses its task). A judge model
from a different family than the generators (Claude Haiku 4.5) does the scoring. The result is a baseline that later
prompt or model changes (for example, the Sonnet-for-Comps/Risk benchmark) can be compared against.

## What Changes

- An evaluation dataset builder that turns a saved research report into Ragas samples. Each sample pairs an agent's
  text with the exact input data that agent received.
- A Ragas runner with Claude Haiku 4.5 as the judge and local MiniLM embeddings, scoring faithfulness for all four LLM
  agents and answer relevancy for the Writer and the Analyst.
- A command that generates live reports for the five test tickers, saves them, scores them and writes per-sample
  scores, a summary table and a dated baseline note.
- An optional `eval` dependency group, so the app itself never installs Ragas, LangChain or PyTorch.

## Capabilities

### New Capabilities

- `ragas-evaluation`: building evaluation samples from reports, scoring them with an LLM judge, and recording results.

### Modified Capabilities

(none)

## Impact

- New package `equity_agent/evaluation/` (sample builder, offline-tested) and the runner `backend/eval/run_ragas.py`.
- New `eval` dependency group: `ragas` 0.4, `sentence-transformers`, and the LangChain 0.3 line that Ragas imports
  (LangChain 1.x removed a module Ragas needs; `langchain-anthropic` is not used because it requires `anthropic<1`).
- New outputs: `backend/eval/reports/<T>.json`, `backend/eval/results/ragas_scores.json`,
  `backend/eval/results/ragas_summary.md`, `docs/<date>-ragas-baseline.md`.
- Cost per full run: about $0.75 for five live reports plus under $0.30 of Haiku judging.
- Depends on `add-research-agents` (reports and agent input builders). Independent of the API and UI changes.
