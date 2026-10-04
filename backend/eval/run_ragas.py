"""Ragas evaluation of the research agents' text (OpenSpec change `add-ragas-evaluation`).

    uv run --group eval python eval/run_ragas.py                    # fresh reports for the 5 test tickers, then score
    uv run --group eval python eval/run_ragas.py --reuse            # score the saved reports again (judge calls only)
    uv run --group eval python eval/run_ragas.py --tickers AAPL JPM
    uv run --group eval python eval/run_ragas.py --snapshot NAME   # also keep scores + summary in eval/runs/NAME

Fresh reports bypass the report and agent caches (so every agent really runs) but keep the market-data cache warm.
Judge: Claude Haiku 4.5, a different model family from the generators (Opus 5.5 / Sonnet 5.5). Embeddings for answer
relevancy: local all-MiniLM-L6-v2. Spends Anthropic credit; never run from pytest.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic
from ragas.embeddings import HuggingFaceEmbeddings
from ragas.llms import llm_factory
from ragas.metrics.collections import AnswerRelevancy, Faithfulness
from ragas.metrics.result import MetricResult

from equity_agent.config import Settings, load_settings
from equity_agent.evaluation.runs import REPORTS_DIR, RESULTS_DIR, SCORES_FILE, SUMMARY_FILE, save_snapshot
from equity_agent.evaluation.samples import RELEVANCY_AGENTS, EvalSample, Skipped, build_samples
from equity_agent.llm import cost_usd
from equity_agent.models import ResearchReport
from equity_agent.pipeline import clear_agent_caches, live_services, run_report

TICKERS = ["AAPL", "NVDA", "JPM", "COST", "TSLA"]
JUDGE_MODEL = "claude-haiku-4-5"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
JUDGE_CONCURRENCY = 4
EST_REPORT_USD = 0.10
EST_SAMPLE_USD = 0.02  # measured: 35 samples cost $0.71 of Haiku (about 4 judge calls per sample)


# ---- judge --------------------------------------------------------------------------------------------------------


class JudgeSpend:
    def __init__(self) -> None:
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    @property
    def usd(self) -> float:
        return cost_usd(JUDGE_MODEL, self.input_tokens, self.output_tokens)


def judge_client(api_key: str, spend: JudgeSpend) -> AsyncAnthropic:
    """An AsyncAnthropic whose `messages.create` accepts what Ragas sends.

    Ragas passes `temperature=0.01` and `top_p=0.1`. anthropic 1.x has no `temperature` argument and current Claude
    models reject temperature together with top_p, so top_p/top_k are dropped and temperature 0 goes through
    `extra_body` (Haiku 4.5 accepts it). Token usage is tallied for the cost report.
    """
    client = AsyncAnthropic(api_key=api_key, max_retries=3)
    original = client.messages.create

    async def create(*args: Any, **kwargs: Any) -> Any:
        extra = dict(kwargs.pop("extra_body", None) or {})
        if kwargs.pop("temperature", None) is not None:
            extra["temperature"] = 0.0
        kwargs.pop("top_p", None)
        kwargs.pop("top_k", None)
        response = await original(*args, extra_body=extra, **kwargs)
        usage = getattr(response, "usage", None)
        spend.calls += 1
        spend.input_tokens += getattr(usage, "input_tokens", 0) or 0
        spend.output_tokens += getattr(usage, "output_tokens", 0) or 0
        return response

    client.messages.create = create  # type: ignore[method-assign]
    return client


class ExplainedFaithfulness(Faithfulness):
    """Ragas faithfulness that also returns the statements the judge found unsupported (as JSON in `reason`)."""

    async def ascore(self, user_input: str, response: str, retrieved_contexts: list[str]) -> MetricResult:
        statements = await self._create_statements(user_input, response)
        if not statements:
            return MetricResult(value=float("nan"))
        verdicts = await self._create_verdicts(statements, "\n".join(retrieved_contexts))
        unsupported = [{"statement": s.statement, "reason": s.reason} for s in verdicts.statements if not s.verdict]
        return MetricResult(
            value=float(self._compute_score(verdicts)),
            reason=json.dumps({"statements": len(verdicts.statements), "unsupported": unsupported}),
        )


def _value(result: MetricResult) -> float | None:
    value = float(result.value)
    return None if math.isnan(value) else round(value, 4)


async def score_samples(samples: list[EvalSample], settings: Settings, spend: JudgeSpend) -> list[dict[str, Any]]:
    client = judge_client(settings.anthropic_api_key, spend)
    llm = llm_factory(JUDGE_MODEL, provider="anthropic", client=client, max_tokens=4096)
    faithfulness = ExplainedFaithfulness(llm=llm)
    relevancy = AnswerRelevancy(llm=llm, embeddings=HuggingFaceEmbeddings(model=EMBEDDING_MODEL))
    semaphore = asyncio.Semaphore(JUDGE_CONCURRENCY)
    scored_at = datetime.now(UTC).isoformat(timespec="seconds")

    async def one(sample: EvalSample) -> dict[str, Any]:
        row: dict[str, Any] = {
            "ticker": sample.ticker,
            "agent": sample.agent,
            "section": sample.section,
            "faithfulness": None,
            "answer_relevancy": None,
            "statements": None,
            "unsupported": [],
            "error": None,
            "response_words": len(sample.response.split()),
            "judge_model": JUDGE_MODEL,
            "scored_at": scored_at,
        }
        async with semaphore:
            try:
                result = await faithfulness.ascore(sample.user_input, sample.response, sample.contexts)
                row["faithfulness"] = _value(result)
                if result.reason:
                    detail = json.loads(result.reason)
                    row["statements"], row["unsupported"] = detail["statements"], detail["unsupported"]
                if sample.agent in RELEVANCY_AGENTS:
                    row["answer_relevancy"] = _value(await relevancy.ascore(sample.user_input, sample.response))
            except Exception as error:  # noqa: BLE001 - one judge failure must not stop the run
                row["error"] = f"{type(error).__name__}: {settings.redact(str(error))[:200]}"
        print(f"  scored {sample.ticker} {sample.agent}/{sample.section}: faithfulness={row['faithfulness']}"
              f" relevancy={row['answer_relevancy']}" + (f" ERROR {row['error']}" if row["error"] else ""))
        return row

    try:
        return await asyncio.gather(*(one(s) for s in samples))
    finally:
        await client.close()


# ---- report generation --------------------------------------------------------------------------------------------


async def generate_report(ticker: str, settings: Settings) -> ResearchReport:
    """A fresh report with every agent running: report and agent caches cleared, data cache kept."""
    services = live_services(settings)
    clear_agent_caches(services.data.cache, ticker)
    try:
        return await run_report(services, ticker)
    finally:
        await services.llm.close()
        services.data.close()


# ---- results ------------------------------------------------------------------------------------------------------


def _mean(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return round(statistics.fmean(present), 3) if present else None


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def summary_markdown(
    rows: list[dict[str, Any]], skipped: list[Skipped], reports: dict[str, ResearchReport], failed: dict[str, str],
    spend: JudgeSpend, generated: bool,
) -> str:  # fmt: skip
    lines = [
        "# Ragas evaluation",
        "",
        f"Run {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}. Judge `{JUDGE_MODEL}`; answer-relevancy embeddings "
        f"`{EMBEDDING_MODEL}`. Reports {'generated fresh (agent caches cleared)' if generated else 'reused from eval/reports'}.",
        "",
        f"Samples scored: {len(rows)}; skipped: {len(skipped)}; judge calls: {spend.calls}, "
        f"{spend.input_tokens:,} input / {spend.output_tokens:,} output tokens, about ${spend.usd:.3f}.",
        "",
        "## By agent",
        "",
        "| Agent | Samples | Faithfulness (mean) | Not scored | Answer relevancy (mean) |",
        "|---|---|---|---|---|",
    ]
    for agent in ("writer", "analyst", "risk", "comps"):
        group = [r for r in rows if r["agent"] == agent]
        if not group:
            continue
        not_scored = sum(1 for r in group if r["faithfulness"] is None)
        relevancy = _fmt(_mean([r["answer_relevancy"] for r in group])) if agent in RELEVANCY_AGENTS else "n/a"
        lines.append(f"| {agent} | {len(group)} | {_fmt(_mean([r['faithfulness'] for r in group]))} | {not_scored} | {relevancy} |")
    lines.append(f"| **all** | {len(rows)} | {_fmt(_mean([r['faithfulness'] for r in rows]))} | "
                 f"{sum(1 for r in rows if r['faithfulness'] is None)} | {_fmt(_mean([r['answer_relevancy'] for r in rows]))} |")

    lines += [
        "",
        "## By ticker",
        "",
        "| Ticker | Signal | Faithfulness | Answer relevancy | Comps ready (s) | Signal ready (s) | Total (s) | LLM calls | Report cost |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for ticker, report in reports.items():
        group = [r for r in rows if r["ticker"] == ticker]
        t = report.timings_ms
        lines.append(
            f"| {ticker} | {report.signal}{'' if report.signal_reviewed else ' (not reviewed)'} | "
            f"{_fmt(_mean([r['faithfulness'] for r in group]))} | {_fmt(_mean([r['answer_relevancy'] for r in group]))} | "
            f"{t.get('comps_ready', 0) / 1000:.1f} | {t.get('signal_ready', 0) / 1000:.1f} | {t.get('total', 0) / 1000:.1f} | "
            f"{len(report.llm_usage)} | ${sum(u.cost_usd for u in report.llm_usage):.3f} |"
        )
    for ticker, reason in failed.items():
        lines.append(f"| {ticker} | failed: {reason} | | | | | | | |")

    lowest = sorted((r for r in rows if r["faithfulness"] is not None), key=lambda r: r["faithfulness"])[:6]
    lines += ["", "## Lowest faithfulness", ""]
    for r in lowest:
        lines.append(f"- **{r['ticker']} {r['agent']}/{r['section']}**: {r['faithfulness']:.3f} "
                     f"({len(r['unsupported'])} of {r['statements']} statements unsupported)")
        for item in r["unsupported"][:4]:
            lines.append(f"  - \"{item['statement']}\" — {item['reason']}")
    errors = [r for r in rows if r["error"]]
    if errors or skipped:
        lines += ["", "## Not scored", ""]
        lines += [f"- {r['ticker']} {r['agent']}/{r['section']}: judge error {r['error']}" for r in errors]
        lines += [f"- {s.ticker} {s.agent}/{s.section}: skipped ({s.reason})" for s in skipped]
    return "\n".join(lines) + "\n"


async def main_async(args: argparse.Namespace) -> int:
    settings = load_settings()
    tickers = [t.upper() for t in args.tickers]
    to_generate = [t for t in tickers if not (args.reuse and (REPORTS_DIR / f"{t}.json").exists())]
    estimate = len(to_generate) * EST_REPORT_USD + len(tickers) * 7 * EST_SAMPLE_USD
    print(f"Evaluating {', '.join(tickers)}: {len(to_generate)} fresh report(s), ~{len(tickers) * 7} samples; "
          f"estimated cost about ${estimate:.2f}")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    reports: dict[str, ResearchReport] = {}
    failed: dict[str, str] = {}
    for ticker in tickers:
        path = REPORTS_DIR / f"{ticker}.json"
        try:
            if ticker in to_generate:
                start = time.perf_counter()
                report = await generate_report(ticker, settings)
                path.write_text(report.model_dump_json(indent=1), encoding="utf-8")
                print(f"{ticker}: report in {time.perf_counter() - start:.1f}s, signal {report.signal}, "
                      f"{len(report.llm_usage)} LLM calls, ${sum(u.cost_usd for u in report.llm_usage):.3f}")
            else:
                report = ResearchReport.model_validate_json(path.read_text(encoding="utf-8"))
                print(f"{ticker}: reusing saved report from {report.generated_at}")
            reports[ticker] = report
        except Exception as error:  # noqa: BLE001 - one ticker failing must not stop the others
            failed[ticker] = settings.redact(f"{type(error).__name__}: {error}")[:200]
            print(f"{ticker}: FAILED {failed[ticker]}")

    samples: list[EvalSample] = []
    skipped: list[Skipped] = []
    for report in reports.values():
        built, missing = build_samples(report)
        samples += built
        skipped += missing
    print(f"Scoring {len(samples)} samples with {JUDGE_MODEL} ({len(skipped)} skipped)")
    spend = JudgeSpend()
    rows = await score_samples(samples, settings, spend)

    (RESULTS_DIR / SCORES_FILE).write_text(
        json.dumps({"judge_model": JUDGE_MODEL, "embedding_model": EMBEDDING_MODEL, "rows": rows,
                    "skipped": [s.model_dump() for s in skipped], "failed": failed}, indent=1, ensure_ascii=False),
        encoding="utf-8",
    )  # fmt: skip
    summary = summary_markdown(rows, skipped, reports, failed, spend, generated=bool(to_generate))
    (RESULTS_DIR / SUMMARY_FILE).write_text(summary, encoding="utf-8")
    print("\n" + summary)
    print(f"Wrote {RESULTS_DIR / SCORES_FILE} and {RESULTS_DIR / SUMMARY_FILE}")
    if args.snapshot:
        print(f"Saved snapshot {save_snapshot(args.snapshot)}")
    return 1 if failed and not reports else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tickers", nargs="+", default=TICKERS)
    parser.add_argument("--reuse", action="store_true", help="score saved reports instead of generating new ones")
    parser.add_argument("--snapshot", metavar="NAME", help="also keep this run's scores and summary in eval/runs/NAME")
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
