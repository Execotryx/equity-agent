"""Real KASE coverage probes and US-listing reports for KASE Global companies.

Run from backend: RUN_LIVE_TESTS=1 uv run pytest -m live tests/test_kase_live.py -q -s
Six native probes use Yahoo only. Three full reports also spend Claude/Tavily
credits. Native coverage gaps are failures, never expected failures or skips.
Evidence is saved in a new timestamped docs/kase-* directory for each run.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from kase_cases import GLOBAL_SOURCE, NATIVE_CASES, SHARES_SOURCE, US_LISTING_CASES, KaseCase, quote_checks

from equity_agent.acceptance import Case, Check, Outcome, evaluate_case
from equity_agent.config import BACKEND_ROOT, Settings, load_settings
from equity_agent.data import DataError, DataLayer, normalize_ticker
from equity_agent.data.market import YahooSource, parse_quote
from equity_agent.llm import Gateway
from equity_agent.models import Quote, ResearchReport, ReportNarrative
from equity_agent.pipeline import RunFailed, Services, run_report

pytestmark = pytest.mark.live


@dataclass
class Evidence:
    directory: Path
    rows: list[dict[str, Any]] = field(default_factory=list)

    def save(self, case: KaseCase, checks: list[Check], elapsed: float, **details: Any) -> None:
        row = {
            **asdict(case), "id": case.id, "source": case.source,
            "passed": all(check.passed for check in checks),
            "checks": [asdict(check) for check in checks], "elapsed_seconds": round(elapsed, 3), **details,
        }
        self.rows.append(row)
        (self.directory / f"{case.id}.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")

    def finish(self) -> None:
        (self.directory / "results.json").write_text(json.dumps(self.rows, indent=2) + "\n", encoding="utf-8")
        lines = [
            "# Live KASE test execution", "", f"Creation: {self.directory.name.removeprefix('kase-').removeprefix('usd-')} (Asia/Qyzylorda)", "",
            "Native cases require the named issuer, declared quote currency and a KASE trading venue.",
            "US-listing cases research KASE-listed companies using US symbols; their prices are not KASE prices.",
            "Native probes apply the app's ticker normalization before calling its Yahoo adapter.", "",
            f"Listing sources: [KASE shares]({SHARES_SOURCE}), [KASE Global]({GLOBAL_SOURCE}).", "",
            "| Company | KASE symbol | Input | Currency | Scope | Result | Failed criteria |",
            "|---|---|---|---|---|---|---|",
        ]
        for row in self.rows:
            failures = "; ".join(check["criterion"] + ": " + check["detail"] for check in row["checks"] if not check["passed"])
            lines.append(f"| {row['company']} | {row['kase_ticker']} | {row['input_ticker']} | {row['currency']} | {row['scope']} | {'PASS' if row['passed'] else 'FAIL'} | {failures} |")
        cost = sum(row.get("acceptance", {}).get("cost_usd", 0) for row in self.rows)
        lines += ["", f"{sum(row['passed'] for row in self.rows)}/{len(self.rows)} cases passed. Recorded Claude cost: ${cost:.4f}.", "",
                  "Pass/fail follows structural acceptance criteria. A reasoned unavailable risk section is allowed;",
                  "narrative quality warnings and performance budgets are diagnostics, not passing criteria.", "",
                  "## Report limitations", ""]
        for row in self.rows:
            report = row.get("report")
            if report:
                risk = report["risks"].get("message", "risk section available")
                warnings = "; ".join(report["quality_warnings"]) or "none"
                budget = "within" if row["acceptance"]["within_budget"] else "over"
                lines.append(f"- {row['input_ticker']}: {risk}. Quality warnings: {warnings}. Performance budget: {budget}.")
        lines += ["", "Each case JSON preserves checks, timings and observed quote details. US-listing JSON also includes",
                  "the complete research report, acceptance results, model usage/cost and quality warnings."]
        (self.directory / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture(scope="module")
def evidence() -> Iterator[Evidence]:
    stamp = datetime.now(timezone(timedelta(hours=5))).strftime("%d-%m-%Y-%H-%M-%S")
    directory = BACKEND_ROOT.parent / "docs" / f"kase-{stamp}"
    directory.mkdir(parents=True, exist_ok=False)
    recorded = Evidence(directory)
    print(f"\nKASE evidence: {directory}", flush=True)
    try:
        yield recorded
    finally:
        recorded.finish()


@pytest.fixture(scope="module")
def settings() -> Settings:
    configured = load_settings()
    assert not configured.offline, "DEMO_OFFLINE must be disabled for live KASE execution"
    return configured


def observe(case: KaseCase) -> tuple[Quote | None, str, list[Check]]:
    try:
        ticker = normalize_ticker(case.input_ticker)
        raw = YahooSource().info(ticker)
        quote = parse_quote(ticker, raw)
        exchange = str(raw.get("fullExchangeName") or raw.get("exchange") or "")
        return quote, exchange, quote_checks(case, quote, exchange)
    except DataError as error:
        criterion = "ticker accepted by application" if error.reason == "invalid ticker" else "quote available"
        return None, "", [Check(criterion, False, error.reason)]
    except Exception as error:
        # Provider exception strings can contain request details; store only their type.
        return None, "", [Check("quote available", False, f"provider exception: {type(error).__name__}")]


def assert_checks(checks: list[Check]) -> None:
    assert all(check.passed for check in checks), "; ".join(
        f"{check.criterion}: {check.detail}" for check in checks if not check.passed
    )


@pytest.mark.parametrize("case", NATIVE_CASES, ids=lambda case: case.id)
def test_native_kase_quote(case: KaseCase, evidence: Evidence) -> None:
    record_quote_case(case, evidence)


def record_quote_case(case: KaseCase, evidence: Evidence) -> None:
    start = time.perf_counter()
    quote, exchange, checks = observe(case)
    evidence.save(case, checks, time.perf_counter() - start, exchange=exchange,
                  quote=quote.model_dump(mode="json") if quote else None)
    assert_checks(checks)


async def fresh_report(settings: Settings, ticker: str) -> Outcome:
    services = Services(data=DataLayer.live(settings, cache_path=None), llm=Gateway(settings), models=settings.agents)
    try:
        services.data.sec.start_parser()
        try:
            return Outcome(report=await run_report(services, ticker, refresh=True))
        except RunFailed as error:
            return Outcome(failure=error.reason)
    finally:
        services.data.close()
        await services.llm.close()


@pytest.mark.parametrize("case", US_LISTING_CASES, ids=lambda case: case.id)
def test_kase_global_company_report(case: KaseCase, settings: Settings, evidence: Evidence) -> None:
    record_report_case(case, settings, evidence)


def record_report_case(case: KaseCase, settings: Settings, evidence: Evidence) -> None:
    start = time.perf_counter()
    quote, exchange, checks = observe(case)
    outcome = asyncio.run(fresh_report(settings, case.input_ticker)) if all(check.passed for check in checks) else Outcome(failure="quote identity check failed")
    acceptance = evaluate_case(Case(case.input_ticker, case.kind), outcome)
    checks += acceptance.checks
    report = outcome.report
    checks.append(Check("writer produced a narrative", isinstance(report, ResearchReport) and isinstance(report.narrative, ReportNarrative),
                        "narrative present" if report and isinstance(report.narrative, ReportNarrative) else "writer unavailable"))
    evidence.save(case, checks, time.perf_counter() - start, exchange=exchange,
                  quote=quote.model_dump(mode="json") if quote else None,
                  acceptance=asdict(acceptance), report=report.model_dump(mode="json") if report else None)
    print(f"\n{case.id}: {len(report.llm_usage) if report else 0} model calls, ${acceptance.cost_usd:.4f}, "
          f"budget={'within' if acceptance.within_budget else 'over or unavailable'}", flush=True)
    assert_checks(checks)
