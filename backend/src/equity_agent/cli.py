"""Command line: `uv run research AAPL [--json] [--refresh]`. Spends Anthropic credit on uncached runs."""

from __future__ import annotations

import argparse
import asyncio
import sys

from equity_agent.config import load_settings
from equity_agent.models import AnalystView, CompsTable, PipelineEvent, ResearchReport, RiskReport, StageError
from equity_agent.pipeline import RunFailed, Services, live_services, run_report
from equity_agent.scoring import scorecard_lines


def _progress(event: PipelineEvent) -> None:
    data = event.data
    if event.event == "stage" and data.get("status") != "started":
        cached = " (cached)" if data.get("cached") else ""
        print(f"  {data['stage']:<13} {data['status']:<6} {data.get('ms', 0):>6} ms{cached}", file=sys.stderr)
    elif event.event == "error" and not data.get("terminal"):
        print(f"  ! {data['stage']}: {data['message']}", file=sys.stderr)


def print_report(report: ResearchReport) -> None:
    snap = report.financials.snapshot
    print(f"\n{snap.name} ({report.ticker})  {snap.currency} {snap.price:,.2f}  —  signal {report.signal}"
          + ("" if report.signal_reviewed else " (preliminary, not reviewed)"))
    if isinstance(report.comps, CompsTable):
        print("peers: " + ", ".join(f"{r.ticker} ({report.comps.peer_origin.get(r.ticker)})" for r in report.comps.peers))
    print("\n".join(scorecard_lines(report.scorecard)))
    if isinstance(report.analyst, AnalystView):
        print(f"\nAnalyst ({report.analyst.confidence:.2f}): {report.analyst.signal_reasoning}")
    if isinstance(report.risks, RiskReport):
        print("\nRisks:")
        print("\n".join(f"  [{risk.severity}] {risk.title} ({risk.category})" for risk in report.risks.risks))
    elif isinstance(report.risks, StageError):
        print(f"\nRisks unavailable: {report.risks.message}")
    print("\n" + report.narrative_markdown)
    print("\nTimings (ms): " + ", ".join(f"{k} {v}" for k, v in report.timings_ms.items()))
    cost = sum(u.cost_usd for u in report.llm_usage)
    print(f"LLM calls: {len(report.llm_usage)}, estimated cost ${cost:.4f}; cache hits: {len(report.cache_hits)}")
    print("\n".join(f"warning: {w}" for w in report.quality_warnings))
    print(report.disclaimer)


async def run(ticker: str, *, as_json: bool, refresh: bool, services: Services | None = None) -> int:
    services = services or live_services(load_settings())
    try:
        report = await run_report(services, ticker, refresh=refresh, on_event=None if as_json else _progress)
    except RunFailed as failure:
        print(f"error: {failure.reason}", file=sys.stderr)
        return 1
    finally:
        await services.llm.close()
        services.data.close()
    print(report.model_dump_json(indent=1) if as_json else "", end="\n" if as_json else "")
    if not as_json:
        print_report(report)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate an equity research report for one ticker.")
    parser.add_argument("ticker")
    parser.add_argument("--json", action="store_true", help="print the report as one JSON document")
    parser.add_argument("--refresh", action="store_true", help="bypass cached reports, peers, quotes and searches")
    args = parser.parse_args(argv)
    return asyncio.run(run(args.ticker, as_json=args.json, refresh=args.refresh))


if __name__ == "__main__":
    sys.exit(main())
