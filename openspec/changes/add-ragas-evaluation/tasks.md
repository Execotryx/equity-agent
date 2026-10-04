# Tasks

## 1. Samples

- [x] 1.1 Add the `eval` dependency group (ragas 0.4.3, sentence-transformers, LangChain 0.3 pins), leaving it out of the default groups; verify `uv sync` without `--group eval` doesn't install ragas, and that `uv run --group eval python -c "import ragas"` works
- [x] 1.2 Implement `equity_agent/evaluation/samples.py` (`EvalSample`, `build_samples(report) -> (samples, skipped)`) using each agent's own input builder, split into one context per top-level key; verify with offline tests on a fixture report: 7 samples, the Writer contexts equal the Writer's `build_user()` input, and the risk sample is skipped with a reason when risks are an error

## 2. Runner

- [x] 2.1 Implement `backend/eval/run_ragas.py`: the Haiku judge via `llm_factory` with the temperature adapter, MiniLM embeddings, faithfulness for all samples and answer relevancy for Writer and Analyst, semaphore 4, `null` for unscoreable samples; verify by type-checking with `uv run --group eval pyright eval`
- [x] 2.2 Add report generation (fresh live run per ticker, caches bypassed, saved to `eval/reports/<T>.json`), the `--reuse` and `--tickers` options, a cost estimate before start, and per-ticker failure isolation; verify `--reuse` with saved reports makes no research calls
- [x] 2.3 Write `eval/results/ragas_scores.json` and `eval/results/ragas_summary.md` (per-agent and per-ticker means, not-scored counts, lowest samples with unsupported statements); verify the files after a run

## 3. Baseline

- [x] 3.1 Run the evaluation live for AAPL, NVDA, JPM, COST and TSLA; verify every ticker is scored or its failure explained
- [x] 3.2 Record the baseline and its caveats in `docs/<date>-ragas-baseline.md`, and add an evaluation section to the README (how to install the group, run it, and read the scores); verify the README command works as written
- [x] 3.3 Run `uv run pytest` and `uv run pyright` without the eval group; verify both pass
