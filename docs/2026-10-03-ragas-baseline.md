# Ragas baseline - 2026-10-03

OpenSpec change `add-ragas-evaluation`. Command: `uv run --group eval python eval/run_ragas.py` (in `backend/`).
Raw per-sample scores: `backend/eval/results/ragas_scores.json`; summary: `backend/eval/results/ragas_summary.md`;
the scored reports: `backend/eval/reports/<T>.json`.

## Setup

- **Reports:** five fresh live reports (AAPL, NVDA, JPM, COST, TSLA). The report and agent caches were cleared and
  the market-data cache was warm, so every agent ran. Generators: Opus 5.5 for Comps, Risk and Analyst; Sonnet 5.5
  for the Writer; effort `low`.
- **Ragas 0.4.3**, modern metric classes:
  - `Faithfulness`: the share of the text's atomic statements that the judge finds supported by the agent's input;
  - `AnswerRelevancy`: how well questions regenerated from the text match the task, by embedding similarity.
- **Judge:** Claude Haiku 4.5 (`claude-haiku-4-5`), a different model family from the generators, temperature 0.
  Same judge as the `llm-as-a-judge` project. Embeddings: local `all-MiniLM-L6-v2`.
- **Samples (7 per report, 35 in total):**
  - each Writer section;
  - the Analyst's view (valuation summary, thesis, counterpoints, reasoning);
  - the Risk Agent's six explanations;
  - the Comps Agent's peer rationales.

  Each sample's "retrieved contexts" are the exact JSON input that agent received, rebuilt with the agent's own
  input builder: there is no retriever in this app.

## Baseline

| Agent | Samples | Faithfulness | Answer relevancy |
|---|---|---|---|
| Writer (Sonnet 5.5) | 20 | **0.950** | 0.392 |
| Analyst (Opus 5.5) | 5 | 0.835 | 0.652 |
| Risk (Opus 5.5) | 5 | 0.724 | n/a |
| Comps (Opus 5.5) | 5 | 0.340 | n/a |
| All | 35 | 0.814 | 0.444 |

| Ticker | Signal | Faithfulness | Comps ready | Total | Report cost |
|---|---|---|---|---|---|
| AAPL | HOLD | 0.795 | 6.6 s | 15.6 s | $0.082 |
| NVDA | BUY | 0.857 | 5.9 s | 16.5 s | $0.085 |
| JPM | BUY | 0.819 | 5.6 s | 14.4 s | $0.085 |
| COST | HOLD | 0.891 | 5.4 s | 16.0 s | $0.081 |
| TSLA | HOLD | 0.707 | 4.9 s | 19.1 s | $0.082 |

- No sample was unscoreable; there were no NaN results this time, unlike the 7 of 20 in the previous project.
- Every report also met the structural acceptance checks: 5 peers, 6 risks quoting real headings, a valid signal,
  420 words or fewer, and no quality warnings from the number-grounding check.
- Judging cost $0.71 (145 Haiku calls, about 4 per sample). The five reports cost $0.42.

## Reading the scores

- **Writer: well grounded (0.95).** 14 of 20 sections scored 1.0, and no section introduced a figure absent from its
  input; the code-side number check agrees. The lowest section was JPM's risk commentary (0.60). It generalised
  "could cause losses" into effects on "earnings, liquidity and capital", and it split one risk ("interest rate and
  credit spread changes") into two.
- **Analyst: 0.835.** Most unsupported statements are judgements, such as "the evidence is balanced" or "leaves
  little room for disappointment". Forming judgements is the Analyst's job, and strict faithfulness penalises them.
  One statement per sample is a sample-construction artifact: the response includes "Final signal: HOLD", the
  Analyst's own decision, which its input cannot contain.
- **Risk: 0.724, with a wide spread** (JPM 1.0, COST 0.96, AAPL 0.73, NVDA 0.71, TSLA 0.22). Low scores come from
  explanations that add consequences the heading doesn't state ("weak EV adoption would directly hurt revenue and
  valuation"). The prompt asks what the heading "implies for the business", which invites this.
- **Comps: 0.34, as the design predicted.** Rationales use the model's industry knowledge ("Intel competes in AI
  accelerators", "Kroger is the largest US grocer") that the five Tavily snippets don't state. A low score here means
  "not grounded in the provided snippets", not "wrong". The peer choices themselves passed every eligibility check.
- **Answer relevancy is low for the Writer (0.39) by construction.** The metric regenerates a question from the
  text and compares it with the task. A section of prose regenerates as "What are Apple's financials?", and that is
  not close in embedding space to an instruction like "Write the financial commentary section… using only the
  provided data". It is useful for comparing runs, not as an absolute measure; the previous project saw the same
  effect.

## Caveats

- **Noise:** re-scoring the same COST report gave 0.887 against 0.891 the first time. Compare means over the five
  tickers, not single samples.
- **Small sample:** 35 samples, one run per ticker, and an LLM judge. Haiku sometimes splits one claim into several
  atomic statements (JPM: "rated 2" became two statements), which magnifies one paraphrase.
- **Only text produced by the LLM agents is scored.** Data, comps math and the scorecard have exact unit tests instead.

## Next levers (not applied)

1. Risk prompt: ask the model to restate the heading's risk in plain words and drop the "what it implies for the
   business" clause. Expected: Risk faithfulness up, TSLA and NVDA especially.
2. Comps prompt: ask rationales to cite the overlap that the search snippets state when they state one, or accept
   the score as a measure of knowledge-based reasoning.
3. Analyst sample: leave the "Final signal" line out of the scored text, so only the reasoning is judged.
4. Benchmark `claude-sonnet-5-5` for Comps and Risk (`add-research-agents` task 4.2) with this evaluation as the
   quality check.

---

# Re-run after the prompt fixes (same day)

Levers 1-3 above were applied:
- **Risk prompt:** explanations restate the heading's risk and add no consequences.
- **Comps prompt:** rationales use the overlap that the search snippets state, otherwise only shared products or
  customers, with no rankings or size claims.
- **Analyst sample:** the final-signal line is no longer scored.

Five fresh reports, same judge. The baseline scores are kept in `backend/eval/runs/2026-10-03-baseline/`. Compare with
`uv run python eval/compare.py 2026-10-03-baseline 2026-10-03-prompt-fixes`.

| Agent | Faithfulness | Answer relevancy |
|---|---|---|
| Writer | 0.950 → 0.940 (-0.010) | 0.392 → 0.399 (+0.007) |
| Analyst | 0.835 → 0.837 (+0.003) | 0.652 → 0.573 (-0.078) |
| Risk | 0.724 → **1.000** (+0.276) | — |
| Comps | 0.340 → 0.446 (+0.106) | — |
| All | 0.814 → **0.863** (+0.049) | 0.444 → 0.434 (-0.010) |

- **Risk: fixed.** All five tickers scored 1.0, TSLA included (0.22 before). Every explanation now stays within its
  heading.
- **Comps: better on average, but uneven.**
  - NVDA rose to 1.0 and AAPL, COST and TSLA improved slightly.
  - JPM fell to 0.09. Following "name only the shared products or customers", the model listed bank products
    ("BAC offers consumer deposits, credit cards, commercial lending, investment banking"). That is accurate, but the
    snippets only name BAC as a competitor, and each product counts as a separate unsupported statement.
  - The remaining gap is structural: rationales rely on knowledge that five search snippets don't contain.
- **Writer and Analyst: unchanged within noise.** Their prompts were not touched; the reports were regenerated, so
  they vary by about ±0.01.
- **Analyst answer relevancy fell 0.08.** This is a side effect of the sample change rather than of the Analyst: the
  scored text no longer starts with the signal, so the questions regenerated from it match the task less closely.
- Report timings and cost are unchanged: 14–17 s total, about $0.08 per report. Judging cost $0.69.

**Next lever for Comps (not applied):** give the agent per-peer evidence, for example the business summaries of
candidate peers, or score the rationales as knowledge rather than grounding. Further prompt wording mostly moves the
problem between tickers, as JPM shows.

---

# Comps Agent with peer business summaries (same day)

The Comps Agent now makes two calls (OpenSpec `add-research-agents` task 2.8):
1. **Pick:** tickers and names, from the target and the search snippets.
2. **Explain:** after the peer quotes are fetched, one rationale per peer, written from the target's and each peer's
   business summary, sector and industry, and the snippets.

The Comps sample now scores the explain call against that input. The previous run is kept in
`backend/eval/runs/2026-10-03-prompt-fixes/`.

| Agent | Baseline | Prompt fixes | + peer summaries |
|---|---|---|---|
| Writer | 0.950 | 0.940 | 0.940 |
| Analyst | 0.835 | 0.837 | 0.839 |
| Risk | 0.724 | 1.000 | 0.985 |
| **Comps** | 0.340 | 0.446 | **0.851** |
| **All** | 0.814 | 0.863 | **0.919** |

Comps faithfulness by ticker went from (0.31, 1.00, 0.09, 0.56, 0.28) to (0.65, 0.92, 0.97, 0.93, 0.78) for AAPL,
NVDA, JPM, COST and TSLA. JPM's rationales now describe bank products that the peers' own summaries state. The
remaining unsupported statements are mostly about products cut off by the 600-character summary limit (Dell's
summary never reaches "personal computers"), or about comparisons the judge wants stated explicitly ("overlaps with
Apple's Mac").

**Cost of the change:**
- **Comps ready:** 7.4–11.6 s, up from 4.8–6.7 s. AAPL's 11.6 s is close to the 12 s budget.
- **Total time:** unchanged at 15–19 s; the Risk branch is still the critical path.
- **Cost:** +$0.017 per uncached report, now about $0.10. Chosen peers and their rationales stay cached for 7 days,
  so repeat runs don't pay it.

**Next lever, not applied:** emit the comps table as soon as it is built and send the rationales afterwards. That
would bring comps-ready back to about 5–7 s, but the UI would have to accept a second comps update.

Risk (1.000 → 0.985) and Writer/Analyst moved within run-to-run noise. Two of ten reports across the last two runs
had a Writer narrative slightly over the 450-word limit (465 and 467 words), each reported as a quality warning.

---

# Comps table before its rationales (same day)

The comps branch now emits the table as soon as it is built. The explain call runs as a background task that only
report assembly waits for, and a second comps event carries the rationales (OpenSpec `add-research-agents`
task 2.9). The previous run is kept in `backend/eval/runs/2026-10-03-two-call-comps/`; this one in
`backend/eval/runs/2026-10-03-early-comps/`.

| Ticker | Comps ready: explain inline → in background | Explain call | Total |
|---|---|---|---|
| AAPL | 11.6 s → **5.3 s** | 4.3 s | 18.6 s → 17.2 s |
| NVDA | 8.7 s → **4.4 s** | 4.2 s | 16.0 s → 15.3 s |
| JPM | 7.9 s → **4.3 s** | 4.1 s | 15.2 s → 14.6 s |
| COST | 9.0 s → **4.2 s** | 4.4 s | 16.3 s → 14.0 s |
| TSLA | 7.4 s → **3.8 s** | 3.8 s | 15.8 s → 15.7 s |

Comps-ready is now faster than the original single-call agent (4.8–6.7 s), because the pick call no longer writes
rationales. No prompt changed, so the scores moved only within run-to-run noise:

| Agent | Writer | Analyst | Risk | Comps | All |
|---|---|---|---|---|---|
| Faithfulness | 0.974 | 0.851 | 0.991 | 0.868 | 0.944 |

Three of the five Writer narratives in this run went slightly over the 450-word limit (456–465 words). It is now
the most frequent quality warning; lowering the prompt's target from 300–400 words would address it.

---

**Storage note (consolidate-duplicated-logic, same day).** Run snapshots now keep scores and summaries only, in
`backend/eval/runs/<name>/`; the latest reports stay in `backend/eval/reports/` for re-scoring. Save one with
`uv run --group eval python eval/run_ragas.py --snapshot NAME`.
