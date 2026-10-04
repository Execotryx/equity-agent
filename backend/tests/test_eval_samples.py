import json

import pytest
from fakes import FakeClaude, make_report

from equity_agent.agents.agents import WriterAgent, WriterInput
from equity_agent.cache import Cache
from equity_agent.evaluation.samples import build_samples, split_contexts
from equity_agent.llm import LlmError
from equity_agent.models import CompsTable, ResearchReport, RiskReport, StageError, YearValue


@pytest.fixture(scope="module")
def report() -> ResearchReport:
    return make_report(FakeClaude())


def test_complete_report_gives_seven_samples(report):
    samples, skipped = build_samples(report)
    assert [(s.agent, s.section) for s in samples] == [
        ("writer", "company_overview"),
        ("writer", "financial_commentary"),
        ("writer", "comps_commentary"),
        ("writer", "risk_commentary"),
        ("analyst", "view"),
        ("risk", "risks"),
        ("comps", "peers"),
    ]
    assert skipped == []
    assert all(s.response and s.contexts and s.user_input for s in samples)


def test_writer_contexts_equal_the_writer_input(report):
    samples, _ = build_samples(report)
    comps = report.comps if isinstance(report.comps, CompsTable) else None
    risks = report.risks.risks if isinstance(report.risks, RiskReport) else None
    expected = WriterAgent().build_user(WriterInput(report.financials, comps, risks, report.news))
    writer = samples[0]
    rebuilt = {k: v for c in writer.contexts for k, v in json.loads(c).items()}
    assert rebuilt == json.loads(expected)


def test_writer_contexts_match_what_the_model_received():
    llm = FakeClaude()
    report = make_report(llm)
    sent = next(user for agent, user in llm.calls if agent == "writer")
    samples, _ = build_samples(report)
    assert split_contexts(sent) == samples[0].contexts


def test_risk_section_unavailable_is_skipped():
    report = make_report(FakeClaude({"risk": [LlmError("refusal", "model declined the request")]}))
    samples, skipped = build_samples(report)
    assert "risk" not in {s.agent for s in samples}
    assert [(s.agent, s.reason) for s in skipped] == [("risk", "risk section unavailable")]


def test_cached_peers_skip_comps_sample(report):
    cached = report.model_copy(update={"cache_hits": [*report.cache_hits, "peers:AAPL:claude-opus-5-5"]})
    _, skipped = build_samples(cached)
    assert [(s.agent, s.reason) for s in skipped] == [("comps", "peers came from the cache")]


def test_failed_narrative_skips_all_writer_samples(report):
    failed = report.model_copy(update={"narrative": StageError(stage="writer", message="boom")})
    samples, skipped = build_samples(failed)
    assert {s.agent for s in samples} == {"analyst", "risk", "comps"}
    assert len([s for s in skipped if s.agent == "writer"]) == 4


def test_cache_delete_prefix():
    cache = Cache(None)
    for key in ("peers:AAPL:claude-opus-5-5", "peers:AAPL:sonnet", "peers:AAPLX:opus", "report:AAPL"):
        cache.set(key, YearValue(year=1, value=1.0), YearValue, None)
    assert cache.delete_prefix("peers:AAPL:") == 2
    assert cache.get("peers:AAPLX:opus", YearValue) is not None
