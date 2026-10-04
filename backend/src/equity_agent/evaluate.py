"""Is the demo ready? `uv run python -m equity_agent.evaluate [--record] [TICKERS...]`.

Runs live reports for the test tickers and edge cases, checks each against the acceptance criteria and writes
`eval/acceptance.{md,json}` (`eval/acceptance-cold.{md,json}` with `--record`). Every agent runs live. It spends
money, so it is never run from pytest.

- Default: the data cache stays warm and agent caches are cleared per ticker.
- `--record`: a cold run (a fresh in-memory cache, so every provider and agent call happens) that also saves the
  offline demo recording to `backend/demo/`.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime

from equity_agent.acceptance import CASES, Case, Outcome, Row, evaluate_case, results_markdown, write_results
from equity_agent.config import BACKEND_ROOT, Settings, load_settings
from equity_agent.demo import Recording, recording_services
from equity_agent.llm import Gateway, LlmClient
from equity_agent.pipeline import RunFailed, Services, clear_agent_caches, live_services, run_report

RESULTS_DIR = BACKEND_ROOT / "eval"
EST_REPORT_USD = 0.10  # measured 2026-10-04: $0.09-0.11 per report with every agent running
TAVILY_PER_REPORT = 2


async def outcome_of(services: Services, case: Case) -> Outcome:
    try:
        return Outcome(report=await run_report(services, case.ticker))
    except RunFailed as error:
        return Outcome(failure=error.reason)


def live_recording_services(settings: Settings, recording: Recording, llm: LlmClient) -> Services:
    from equity_agent.data import market, search, sec

    sec.configure(settings.edgar_identity)
    return recording_services(
        recording,
        llm,
        market=market.YahooSource(),
        filings=sec.EdgarSource(settings.edgar_identity),
        search=search.TavilySource(settings.tavily_api_key),
        settings=settings,
    )


async def run_cases(settings: Settings, cases: list[Case], record: bool) -> list[Row]:
    rows: list[Row] = []
    if record:
        recording = Recording()
        services = live_recording_services(settings, recording, Gateway(settings))
        services.data.sec.start_parser()  # filings parse in the worker, as in the API
        try:
            for case in cases:
                recording.start(case.ticker.replace(".", "-"))
                outcome = await outcome_of(services, case)
                recording.save()
                rows.append(report_row(case, outcome))
        finally:
            services.data.close()
            await services.llm.close()
        return rows

    services = live_services(settings)
    services.data.sec.start_parser()
    try:
        for case in cases:
            clear_agent_caches(services.data.cache, case.ticker.replace(".", "-"))
            rows.append(report_row(case, await outcome_of(services, case)))
    finally:
        services.data.close()
        await services.llm.close()
    return rows


def report_row(case: Case, outcome: Outcome) -> Row:
    row = evaluate_case(case, outcome)
    status = "pass" if row.passed else "FAIL (" + "; ".join(row.failed) + ")"
    print(f"{case.ticker:<7} {status}", flush=True)
    return row


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--record", action="store_true", help="cold run that also saves the offline demo recording")
    parser.add_argument("tickers", nargs="*", help="a subset of the test cases (default: all)")
    args = parser.parse_args(argv)
    wanted = {t.upper() for t in args.tickers}
    cases = [c for c in CASES if not wanted or c.ticker in wanted]
    if not cases:
        parser.error(f"no test case among {', '.join(sorted(wanted))}; cases: {', '.join(c.ticker for c in CASES)}")

    settings = load_settings()
    if settings.offline:
        parser.error("DEMO_OFFLINE is set; the evaluation needs the live services")
    reports = sum(c.kind != "not_found" for c in cases)
    print(
        f"Evaluating {len(cases)} cases ({reports} full reports{', recording' if args.record else ''}): "
        f"about ${reports * EST_REPORT_USD:.2f} of Claude and {reports * TAVILY_PER_REPORT} Tavily credits.",
        flush=True,
    )
    rows = asyncio.run(run_cases(settings, cases, args.record))
    mode = "cold, recorded for offline" if args.record else "warm data cache"
    title = f"Acceptance run {datetime.now(UTC):%Y-%m-%d %H:%M} UTC ({mode})"
    md, js = write_results(rows, RESULTS_DIR, title, "acceptance-cold" if args.record else "acceptance")
    print()
    print(results_markdown(rows, title))
    print(f"Wrote {md.relative_to(BACKEND_ROOT)} and {js.relative_to(BACKEND_ROOT)}")
    return 0 if all(r.passed for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
