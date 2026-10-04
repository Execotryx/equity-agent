import asyncio
import json

import pytest
from fakes import FakeClaude, default_output

from equity_agent.agents.agents import (
    AnalystAgent,
    AnalystInput,
    CompsAgent,
    CompsExplainAgent,
    CompsInput,
    ExplainInput,
    RiskAgent,
    RiskInput,
    WriterAgent,
    WriterInput,
    build_profile,
    parse_sections,
    ungrounded_numbers,
)
from equity_agent.agents.base import StageFailed
from equity_agent.data import DataLayer
from equity_agent.models import (
    AnalystOutput,
    FactorScore,
    PeerPick,
    PeerPicks,
    PeerRationale,
    PeerRationales,
    RiskItem,
    RiskSelection,
    Scorecard,
    SearchResults,
    Signal,
)
from equity_agent.scoring import build_comps_table, select_peers


@pytest.fixture(scope="module")
def data() -> DataLayer:
    return DataLayer.recorded()


# ---- Financial Data Agent -------------------------------------------------------------------------------------


def test_financial_profile_without_llm(data):
    quote, history = data.market.quote("COST").value, data.market.history("COST").value
    profile = build_profile(quote, history)
    assert profile.snapshot.ticker == "COST" and len(profile.revenue_history) >= 3 and len(profile.price_history) >= 240


# ---- base: validate -> re-ask -> fail -------------------------------------------------------------------------


def comps_input(data) -> CompsInput:
    snap = data.market.quote("COST").value.snapshot
    found = data.search.competitors(snap.name, snap.industry).value
    assert isinstance(found, SearchResults)
    return CompsInput(snapshot=snap, search=found.items)


def picks(*tickers: str) -> PeerPicks:
    return PeerPicks(peers=[PeerPick(ticker=t, name=t) for t in tickers])


def test_valid_first_answer(data):
    llm = FakeClaude({"comps": [picks("WMT", "TGT", "BJ")]})
    result = asyncio.run(CompsAgent().run(llm, comps_input(data)))
    assert [p.ticker for p in result.output.peers] == ["WMT", "TGT", "BJ"] and len(result.usages) == 1


def test_invalid_answer_fixed_on_reask(data):
    llm = FakeClaude({"comps": [picks("WMT", "COST"), picks("WMT", "TGT", "BJ")]})
    result = asyncio.run(CompsAgent().run(llm, comps_input(data)))
    assert len(result.usages) == 2
    assert "do not include the target COST" in llm.calls[1][1]


def test_still_invalid_after_reask_fails(data):
    llm = FakeClaude({"comps": [picks("WMT"), picks("WMT")]})
    with pytest.raises(StageFailed, match="return 3 to 5 peers") as caught:
        asyncio.run(CompsAgent().run(llm, comps_input(data)))
    assert len(caught.value.usages) == 2


def explain_input(data) -> ExplainInput:
    target = data.market.quote("COST").value
    batch = data.market.peers(["WMT", "TGT", "BJ"]).value
    table = build_comps_table(target, select_peers(target, ["WMT", "TGT", "BJ"], batch.quotes, batch.failed))
    return ExplainInput(target.snapshot, table.peers, [])


def rationales(**by_ticker: str) -> PeerRationales:
    return PeerRationales(rationales=[PeerRationale(ticker=t, rationale=r) for t, r in by_ticker.items()])


def test_explain_input_has_every_peer_summary(data):
    payload = json.loads(CompsExplainAgent().build_user(explain_input(data)))
    assert [p["ticker"] for p in payload["peers"]] == ["WMT", "TGT", "BJ"]
    assert all(p["business_summary"] for p in payload["peers"]) and payload["company"]["business_summary"]


def test_explain_rules(data):
    agent, data_in = CompsExplainAgent(), explain_input(data)
    assert agent.validate(rationales(WMT="Grocery.", TGT="Retail.", BJ="Warehouse club."), data_in) == []
    assert any("exactly one rationale" in p for p in agent.validate(rationales(WMT="x", TGT="y"), data_in))
    long = agent.validate(rationales(WMT="word " * 21, TGT="y", BJ="z"), data_in)
    assert any("20 words" in p for p in long)


def test_explain_uses_its_own_prompt():
    assert CompsExplainAgent().system != CompsAgent().system and CompsExplainAgent.name == "comps"


def test_comps_input_is_compact_sorted_json(data):
    user = CompsAgent().build_user(comps_input(data))
    payload = json.loads(user)
    assert payload["company"]["ticker"] == "COST" and payload["search_results"]
    assert user == json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# ---- Risk Agent -----------------------------------------------------------------------------------------------


def risk_input(data) -> RiskInput:
    headings = data.sec.risk_headings("AAPL").value
    return RiskInput("Apple Inc.", "AAPL", "10-K", headings.headings)


def test_risk_selection_valid(data):
    agent_input = risk_input(data)
    selection = default_output(RiskSelection, json.loads(RiskAgent().build_user(agent_input)))
    assert RiskAgent().validate(selection, agent_input) == []  # type: ignore[arg-type]


def test_five_risks_fixed_on_reask(data):
    agent_input = risk_input(data)
    full = default_output(RiskSelection, json.loads(RiskAgent().build_user(agent_input)))
    assert isinstance(full, RiskSelection)
    five = RiskSelection(risks=full.risks[:5])
    llm = FakeClaude({"risk": [five, full]})
    result = asyncio.run(RiskAgent().run(llm, agent_input))
    assert len(result.output.risks) == 6 and len(result.usages) == 2


def test_risk_heading_must_be_verbatim(data):
    agent_input = risk_input(data)
    item = RiskItem(title="Made up", category="other", severity=1, explanation="x", source_heading="Invented heading text")
    problems = RiskAgent().validate(RiskSelection(risks=[item] * 6), agent_input)
    assert any("verbatim" in p for p in problems)


# ---- Analyst Agent --------------------------------------------------------------------------------------------


def analyst_input(data, preliminary: Signal = "HOLD") -> AnalystInput:
    quote, history = data.market.quote("AAPL").value, data.market.history("AAPL").value
    card = Scorecard(factors=[FactorScore(name="valuation", score=0, detail="x")], total=0, preliminary_signal=preliminary)
    return AnalystInput(build_profile(quote, history), None, None, card, [])


def view(signal="HOLD", changed=False, reason=None, **overrides) -> AnalystOutput:
    base = dict(
        signal=signal, confidence=0.6, changed_from_preliminary=changed, change_reason=reason,
        valuation_summary="Fair.", thesis=["a", "b", "c"], counterpoints=["d", "e", "f"], signal_reasoning="Because.",
    )  # fmt: skip
    return AnalystOutput(**{**base, **overrides})


def test_signal_confirmed(data):
    assert AnalystAgent().validate(view(), analyst_input(data)) == []


def test_one_step_change_with_reason_accepted(data):
    assert AnalystAgent().validate(view("BUY", True, "New product cycle."), analyst_input(data)) == []


def test_two_step_change_rejected(data):
    problems = AnalystAgent().validate(view("BUY", True, "x"), analyst_input(data, "SELL"))
    assert any("at most one step" in p for p in problems)


def test_change_without_reason_rejected(data):
    problems = AnalystAgent().validate(view("BUY", True, None), analyst_input(data))
    assert any("change_reason" in p for p in problems)


def test_counts_and_confidence_checked(data):
    problems = AnalystAgent().validate(view(thesis=["a"], confidence=1.5), analyst_input(data))
    assert any("exactly 3" in p for p in problems) and any("confidence" in p for p in problems)


# ---- Writer Agent ---------------------------------------------------------------------------------------------

GOOD = """## Company overview
Apple sells phones.
## Financial commentary
Revenue reached $416.16B.
## Comps commentary
Forward P/E of 34.8 is a +59% premium.
## Risk commentary
Six risks, the 52-week range and the 10-K matter.
"""


def test_writer_sections_parsed():
    narrative, problems = parse_sections(GOOD)
    assert problems == []
    assert narrative.comps_commentary.startswith("Forward P/E")


def test_writer_missing_section_and_signal_flagged():
    narrative, problems = parse_sections("## Company overview\nWe rate it a BUY.\n")
    assert "missing section: risk commentary" in problems
    assert any("recommendation" in p for p in problems)


def test_writer_input_has_no_signal(data):
    quote, history = data.market.quote("AAPL").value, data.market.history("AAPL").value
    user = WriterAgent().build_user(WriterInput(build_profile(quote, history), None, None, []))
    assert "preliminary_signal" not in user and "scorecard" not in user


def test_invented_number_flagged_rounding_allowed():
    source = '{"revenue":"$416.16B","pe":"34.8","premium":"+59%"}'
    assert ungrounded_numbers(GOOD, source) == []
    assert ungrounded_numbers("Margins hit 31.7% and revenue $416.2B.", source) == ["31.7"]


def test_model_tickers_use_the_shared_normaliser(data):
    agent, data_in = CompsAgent(), comps_input(data)
    assert agent.validate(picks("brk.b", "WMT", "TGT"), data_in) == []
    assert agent.validate(picks("cost", "WMT", "TGT"), data_in) == ["do not include the target COST"]
    problems = agent.validate(picks("$$$", "WMT", "TGT"), data_in)
    assert problems[0] == "invalid ticker symbols: $$$"


def test_explain_accepts_lower_case_tickers(data):
    assert CompsExplainAgent().validate(rationales(wmt="Grocery.", tgt="Retail.", bj="Club."), explain_input(data)) == []
