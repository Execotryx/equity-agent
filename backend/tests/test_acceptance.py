import json

import pytest
from fakes import FakeClaude, make_report

from equity_agent.acceptance import CASES, Case, Outcome, evaluate_case, write_results
from equity_agent.llm import LlmError
from equity_agent.models import CompsTable, StageError


@pytest.fixture(scope="module")
def aapl():
    return make_report(FakeClaude(), "AAPL")


@pytest.fixture(scope="module")
def jpm():
    return make_report(FakeClaude(), "JPM")


def test_good_reports_pass(aapl, jpm):
    assert evaluate_case(Case("AAPL"), Outcome(report=aapl)).passed
    row = evaluate_case(Case("JPM", "bank"), Outcome(report=jpm))
    assert row.passed, row.failed
    assert {"financials metric set", "no EV/EBITDA"} <= {c.criterion for c in row.checks}


def test_a_broken_report_fails_with_the_criterion_named(aapl):
    assert isinstance(aapl.comps, CompsTable)
    broken = aapl.model_copy(
        update={
            "comps": aapl.comps.model_copy(update={"rows": aapl.comps.rows[:2]}),  # target and one peer
            "disclaimer": "",
        }
    )
    row = evaluate_case(Case("AAPL"), Outcome(report=broken))
    assert not row.passed
    assert row.failed == ["at least 3 peers with 2+ valuation multiples", "disclaimer present"]
    assert next(c for c in row.checks if not c.passed).detail == "1 of 1 peers"


def test_an_unreviewed_signal_fails(aapl):
    unreviewed = aapl.model_copy(update={"analyst": StageError(stage="analyst", message="analyst unavailable")})
    assert evaluate_case(Case("AAPL"), Outcome(report=unreviewed)).failed == ["signal with reasoning"]


def test_a_bank_with_the_general_metric_set_fails(aapl):
    row = evaluate_case(Case("JPM", "bank"), Outcome(report=aapl))
    assert row.failed == ["financials metric set", "no EV/EBITDA"]


def test_a_failed_risk_section_passes_when_it_gives_a_reason():
    report = make_report(FakeClaude({"risk": [LlmError("refusal", "model declined the request")]}), "COST")
    row = evaluate_case(Case("COST"), Outcome(report=report))
    assert row.passed, row.failed


def test_edge_cases(aapl):
    assert evaluate_case(Case("ZZZZQX", "not_found"), Outcome(failure="ticker not found")).passed
    assert not evaluate_case(Case("ZZZZQX", "not_found"), Outcome(report=aapl)).passed
    assert not evaluate_case(Case("BRK.B", "class_share"), Outcome(report=aapl)).passed
    brk = aapl.model_copy(update={"ticker": "BRK-B"})
    assert evaluate_case(Case("BRK.B", "class_share"), Outcome(report=brk)).passed
    reasoned = aapl.model_copy(update={"risks": StageError(stage="risk", message="no risk-factor section found in the 20-F")})
    assert evaluate_case(Case("TSM", "foreign_filer"), Outcome(report=reasoned)).passed
    assert not evaluate_case(Case("TSM", "foreign_filer"), Outcome(report=aapl)).passed  # a 10-K, not a 20-F


def test_the_matrix_covers_the_plan():
    assert [c.ticker for c in CASES] == ["AAPL", "NVDA", "JPM", "COST", "TSLA", "ZZZZQX", "BRK.B", "TSM"]


def test_results_files(aapl, tmp_path):
    slow = aapl.model_copy(update={"timings_ms": {**aapl.timings_ms, "total": 31_000}})
    rows = [
        evaluate_case(Case("AAPL"), Outcome(report=aapl)),
        evaluate_case(Case("NVDA"), Outcome(report=slow)),
        evaluate_case(Case("ZZZZQX", "not_found"), Outcome(failure="ticker not found")),
    ]
    md, js = write_results(rows, tmp_path, "Test run")
    table = md.read_text(encoding="utf-8").splitlines()
    assert table[0] == "### Test run"
    assert table[2].startswith("| Ticker | Result | Signal | Peers | Comps ready | Total | LLM calls | Cost | Budget |")
    assert table[4].startswith("| AAPL | pass |") and table[4].endswith("| within |")
    assert table[5].endswith("| OVER |")
    assert table[6].startswith("| ZZZZQX | pass | — |")
    assert table[7].startswith("| **Total** | 3/3 pass |") and table[7].endswith("| 1 over |")
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["totals"] == {"passed": 3, "cases": 3, "llm_calls": rows[0].llm_calls * 2, "cost_usd": data["totals"]["cost_usd"], "over_budget": 1}
    assert data["rows"][0]["total_ms"] == aapl.timings_ms["total"]  # timings come from the report
