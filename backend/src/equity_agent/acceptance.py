"""Acceptance criteria for the test tickers (IMPLEMENTATION_PLAN.md §9.1) as pure checks over a run's outcome.

`evaluate.py` produces the outcomes live; tests feed it FakeClaude reports. Each failed check names its criterion.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from equity_agent.formatting import POSITIVE_ONLY, meaningful
from equity_agent.models import DISCLAIMER, AnalystView, CompsTable, ResearchReport, RiskReport, StageError

Kind = Literal["standard", "bank", "not_found", "class_share", "foreign_filer"]

# §9.3 performance budget for a report whose agents all run (comps table, then the whole report).
COMPS_BUDGET_MS = 12_000
TOTAL_BUDGET_MS = 30_000
MIN_PEERS = 3
MIN_MULTIPLES = 2


@dataclass(frozen=True)
class Case:
    ticker: str
    kind: Kind = "standard"
    note: str = ""


CASES = [
    Case("AAPL", note="large-cap baseline"),
    Case("NVDA", note="high growth, very high multiples"),
    Case("JPM", "bank", "financials metric set"),
    Case("COST", note="stable retail"),
    Case("TSLA", note="auto/tech ambiguity"),
    Case("ZZZZQX", "not_found", "unknown ticker"),
    Case("BRK.B", "class_share", "class share resolves to BRK-B"),
    Case("TSM", "foreign_filer", "20-F filer"),
]


@dataclass
class Outcome:
    """What a run produced: a report, or the reason it ended early."""

    report: ResearchReport | None = None
    failure: str | None = None  # the terminal error's reason


@dataclass
class Check:
    criterion: str
    passed: bool
    detail: str = ""


@dataclass
class Row:
    ticker: str
    kind: Kind
    passed: bool
    failed: list[str] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    signal: str | None = None
    peers: int | None = None
    comps_ready_ms: int | None = None
    total_ms: int | None = None
    llm_calls: int = 0
    cost_usd: float = 0.0
    within_budget: bool | None = None  # None when no report was built
    timings_ms: dict[str, int] = field(default_factory=dict)  # every stage, to explain a row over budget


def valuation_multiples(table: CompsTable) -> list[str]:
    return [m for m in table.metrics if m in POSITIVE_ONLY]


def peers_with_multiples(table: CompsTable) -> int:
    metrics = valuation_multiples(table)
    return sum(
        1
        for row in table.peers
        if sum(meaningful(m, getattr(row.multiples, m)) is not None for m in metrics) >= MIN_MULTIPLES
    )


def standard_checks(report: ResearchReport) -> list[Check]:
    profile = report.financials
    multiples = sum(v is not None for v in profile.multiples.model_dump().values())
    checks = [
        Check(
            "price and key financials present",
            profile.snapshot.price > 0 and bool(profile.revenue_history) and multiples >= 3,
            f"price {profile.snapshot.price}, {len(profile.revenue_history)} years of revenue, {multiples} multiples",
        )
    ]
    comps = report.comps
    if isinstance(comps, CompsTable):
        good = peers_with_multiples(comps)
        checks.append(
            Check(
                f"at least {MIN_PEERS} peers with {MIN_MULTIPLES}+ valuation multiples",
                good >= MIN_PEERS,
                f"{good} of {len(comps.peers)} peers",
            )
        )
    else:
        checks.append(Check(f"at least {MIN_PEERS} peers with {MIN_MULTIPLES}+ valuation multiples", False, comps.message))
    analyst = report.analyst
    reasoned = isinstance(analyst, AnalystView) and bool(analyst.signal_reasoning.strip())
    checks.append(
        Check(
            "signal with reasoning",
            report.signal in ("BUY", "HOLD", "SELL") and reasoned,
            report.signal if reasoned else f"{report.signal}, not reviewed ({_message(analyst)})",
        )
    )
    risks = report.risks
    checks.append(
        Check(
            "risk section present or unavailable with a reason",
            (isinstance(risks, RiskReport) and bool(risks.risks)) or (isinstance(risks, StageError) and bool(risks.message)),
            f"{len(risks.risks)} risks from the {risks.filing.form}" if isinstance(risks, RiskReport) else risks.message,
        )
    )
    checks.append(Check("disclaimer present", report.disclaimer == DISCLAIMER))
    return checks


def _message(section: object) -> str:
    return section.message if isinstance(section, StageError) else "missing"


def check(case: Case, outcome: Outcome) -> list[Check]:
    report = outcome.report
    if case.kind == "not_found":
        return [Check("clear not-found error", outcome.failure == "ticker not found", outcome.failure or "a report was built")]
    if report is None:
        return [Check("report produced", False, outcome.failure or "no report")]
    if case.kind == "class_share":
        return [
            Check("class share resolves", report.ticker == "BRK-B", report.ticker),
            Check("disclaimer present", report.disclaimer == DISCLAIMER),
        ]
    if case.kind == "foreign_filer":
        risks = report.risks
        from_20f = isinstance(risks, RiskReport) and risks.filing.form == "20-F" and bool(risks.risks)
        reasoned = isinstance(risks, StageError) and bool(risks.message)
        detail = f"{len(risks.risks)} risks from the {risks.filing.form}" if isinstance(risks, RiskReport) else risks.message
        return [
            Check("risks from the 20-F or a reasoned unavailability", from_20f or reasoned, detail),
            Check("disclaimer present", report.disclaimer == DISCLAIMER),
        ]
    checks = standard_checks(report)
    if case.kind == "bank":
        comps = report.comps
        metric_set = comps.metric_set if isinstance(comps, CompsTable) else None
        checks.append(Check("financials metric set", metric_set == "financials", str(metric_set)))
        checks.append(
            Check(
                "no EV/EBITDA",
                isinstance(comps, CompsTable) and "ev_ebitda" not in comps.metrics,
                ", ".join(comps.metrics) if isinstance(comps, CompsTable) else "no comps",
            )
        )
    return checks


def evaluate_case(case: Case, outcome: Outcome) -> Row:
    checks = check(case, outcome)
    row = Row(
        ticker=case.ticker,
        kind=case.kind,
        passed=all(c.passed for c in checks),
        failed=[c.criterion for c in checks if not c.passed],
        checks=checks,
    )
    report = outcome.report
    if report is not None:
        timings = report.timings_ms
        row.signal = report.signal
        row.timings_ms = dict(timings)
        row.peers = len(report.comps.peers) if isinstance(report.comps, CompsTable) else 0
        row.comps_ready_ms = timings.get("comps_ready")
        row.total_ms = timings.get("total")
        row.llm_calls = len(report.llm_usage)
        row.cost_usd = round(sum(u.cost_usd for u in report.llm_usage), 4)
        row.within_budget = (row.comps_ready_ms is None or row.comps_ready_ms <= COMPS_BUDGET_MS) and (
            row.total_ms is not None and row.total_ms <= TOTAL_BUDGET_MS
        )
    return row


# ---- results files ------------------------------------------------------------------------------------------------


def _seconds(ms: int | None) -> str:
    return "—" if ms is None else f"{ms / 1000:.1f} s"


def results_markdown(rows: list[Row], title: str) -> str:
    lines = [
        f"### {title}",
        "",
        "| Ticker | Result | Signal | Peers | Comps ready | Total | LLM calls | Cost | Budget |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        result = "pass" if r.passed else "FAIL: " + "; ".join(r.failed)
        budget = "—" if r.within_budget is None else "within" if r.within_budget else "OVER"
        lines.append(
            f"| {r.ticker} | {result} | {r.signal or '—'} | {'—' if r.peers is None else r.peers} | "
            f"{_seconds(r.comps_ready_ms)} | {_seconds(r.total_ms)} | {r.llm_calls} | ${r.cost_usd:.3f} | {budget} |"
        )
    passed = sum(r.passed for r in rows)
    over = sum(r.within_budget is False for r in rows)
    lines.append(
        f"| **Total** | {passed}/{len(rows)} pass | | | | | {sum(r.llm_calls for r in rows)} | "
        f"${sum(r.cost_usd for r in rows):.3f} | {over} over |"
    )
    lines += ["", f"Budget: comps table ≤ {COMPS_BUDGET_MS // 1000} s and report ≤ {TOTAL_BUDGET_MS // 1000} s, every agent running."]
    return "\n".join(lines) + "\n"


def write_results(rows: list[Row], directory: Path, title: str, name: str = "acceptance") -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    md = directory / f"{name}.md"
    js = directory / f"{name}.json"
    md.write_text(results_markdown(rows, title), encoding="utf-8")
    totals = {
        "passed": sum(r.passed for r in rows),
        "cases": len(rows),
        "llm_calls": sum(r.llm_calls for r in rows),
        "cost_usd": round(sum(r.cost_usd for r in rows), 4),
        "over_budget": sum(r.within_budget is False for r in rows),
    }
    js.write_text(json.dumps({"title": title, "rows": [asdict(r) for r in rows], "totals": totals}, indent=1) + "\n", encoding="utf-8")
    return md, js
