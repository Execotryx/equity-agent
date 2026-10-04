# Design

## Context

The previous cohort project (`../llm-as-a-judge`) evaluated a RAG chatbot with Ragas 0.1.21. It used faithfulness and
answer relevancy, a Claude Haiku judge and `all-MiniLM-L6-v2` embeddings. That approach carries over, with two
differences. First, this app has no retriever: the "retrieved contexts" are the compact JSON blocks each agent
receives. Second, this project uses `anthropic` 1.x and Python 3.13.

## Goals / Non-Goals

**Goals:**
- Reuse the agents' own input builders, so that the judge sees exactly what the generator saw.
- Offline tests for sample building; live judging only on request.

**Non-Goals:**
- Reference-based metrics (answer correctness, context recall). There are no ground-truth reports.
- Gating CI on scores. Scores are a baseline for comparison, not pass/fail criteria.
- Evaluating the deterministic stages (data, comps math, scorecard), which have exact unit tests.

## Decisions

- **Ragas 0.4.3, modern metric classes** (`ragas.metrics.collections.Faithfulness`, `AnswerRelevancy`), each scored
  per sample with `ascore()`. The legacy `evaluate()` path, which still goes through LangChain wrappers, is not used.
- **Judge through Ragas `llm_factory("claude-haiku-4-5-20251001", provider="anthropic", client=AsyncAnthropic)`**,
  which uses instructor.
  - Ragas sends `temperature=0.01` and `top_p=0.1`. `anthropic` 1.x has no `temperature` argument, and current Claude
    models reject `temperature` together with `top_p`.
  - A small adapter on the judge client's `messages.create` therefore drops `top_p` and `top_k`, and sends
    `temperature: 0` through `extra_body`. Haiku 4.5 accepts temperature.
  - Verified live on 2026-10-03: one sample scored in about 15 s.
  - Considered: `langchain-anthropic` with `LangchainLLMWrapper`. Rejected, because every 0.3.x release requires
    `anthropic<1`, which conflicts with the app.
- **Embeddings:** `ragas.embeddings.HuggingFaceEmbeddings("sentence-transformers/all-MiniLM-L6-v2")`, running
  locally on CPU, as in the previous project.
- **Dependency group `eval`** (not installed by default):
  - `ragas`, `sentence-transformers`, and `langchain`, `langchain-core`, `langchain-community` and
    `langchain-openai` pinned to `>=0.3,<0.4`;
  - Ragas 0.4.3 imports `langchain_community.chat_models.vertexai`, which no longer exists in langchain-community
    0.4+ (the same incompatibility as in the previous project);
  - run with `uv run --group eval python eval/run_ragas.py`.
- **Code split.**
  - `equity_agent/evaluation/samples.py` is pure, has no Ragas import, and is covered by offline tests. It turns a
    `ResearchReport` into `EvalSample(ticker, agent, section, user_input, response, contexts)`.
  - `backend/eval/run_ragas.py` holds the Ragas runner. It sits outside `src/` so that pyright and pytest don't need
    the `eval` group. It is type-checked with `uv run --group eval pyright eval`.
- **Contexts = the agent's input, rebuilt by the agent's own `build_user()` from the report**, then split into one
  context string per top-level JSON key (profile, comps, risks, scorecard, news). This keeps each context small
  enough for the judge's statement-verification prompt. The report stores everything the builders need.
- **The Analyst sample scores the reasoning, not the decision.** Its response is the valuation summary, thesis,
  counterpoints, signal reasoning and any change reason. The final signal is left out because it is the Analyst's
  own output, which its input cannot contain; the baseline showed one unsupported statement per sample from it.
- **The Comps sample scores the explain call.** Its contexts are that call's input (target summary, peer summaries,
  search snippets), rebuilt from the report: the comps table keeps each row's business summary.
- **Task descriptions (`user_input`)** are fixed strings per agent and section, for example "Write the comps
  commentary section of an equity research report on COST using only the provided data."
- **Concurrency:** samples are scored with `asyncio.gather` under a semaphore of 4, matching the app's Claude
  concurrency limit.
- **NaN handling:** a sample whose faithfulness can't be computed (no claims) is stored as `null`. It is excluded from
  means and counted, because the previous project showed that dropped NaNs silently flatter a model.

## Risks / Trade-offs

- [Peer rationales draw on the model's general knowledge (for example "competes in cloud"), which the search snippets
  may not state] → The Comps sample is reported separately. A low score there means "not grounded in the provided
  snippets", not "wrong".
- [Judge noise: scores move by a few hundredths between runs] → Each run records the judge model and the time, and
  the summary states the sample count. Compare runs on means across five tickers, not single samples.
- [Haiku may split numeric statements differently from a human reader] → The lowest-scoring samples are listed with
  their unsupported statements, for manual review.
- [PyTorch is large (sentence-transformers)] → It lives only in the optional `eval` group.
