import asyncio
import json
import time

import pytest
from fakes import FakeClaude, collect_events, fake_services
from sec_helpers import FixtureFilingSource

from equity_agent.agents.agents import PEERS_FALLBACK
from equity_agent.data import DataLayer
from equity_agent.data.sec import SecData
from equity_agent.llm import LlmError
from equity_agent.models import AnalystView, CompsTable, PeerPick, PeerPicks, RiskReport, StageError
from equity_agent.models import PeerChoice
from equity_agent.pipeline import Services, report_from_event


def stage_events(events, status):
    return [(i, e.data["stage"]) for i, e in enumerate(events) if e.event == "stage" and e.data["status"] == status]


def test_event_order_and_single_report():
    events = collect_events(fake_services(FakeClaude()))
    kinds = [e.event for e in events]
    assert kinds[-1] == "report" and kinds.count("report") == 1
    first_narrative = kinds.index("narrative")
    comps_partial = next(i for i, e in enumerate(events) if e.event == "partial" and e.data["key"] == "comps")
    assert comps_partial < first_narrative
    report = report_from_event(events[-1])
    assert isinstance(report.comps, CompsTable) and isinstance(report.risks, RiskReport)
    assert isinstance(report.analyst, AnalystView) and report.signal_reviewed
    assert report.disclaimer == "Educational project - not investment advice."
    assert {"comps_ready", "signal_ready", "total", "risk", "writer"} <= set(report.timings_ms)
    assert [u.agent for u in report.llm_usage].count("writer") == 1 and len(report.llm_usage) == 5  # comps: pick + explain


def test_branches_start_before_any_finishes():
    events = collect_events(fake_services(FakeClaude(delay=0.05)))
    branches = {"financials", "comps", "risk", "news"}
    started = {s: i for i, s in stage_events(events, "started") if s in branches}
    first_done = min(i for i, s in stage_events(events, "done") if s in branches)
    assert set(started) == branches and max(started.values()) < first_done


def test_analyst_and_writer_overlap():
    llm = FakeClaude(delay=0.1)
    collect_events(fake_services(llm))
    (a_start, a_end), (w_start, w_end) = llm.spans["analyst"][0], llm.spans["writer"][0]
    assert a_start < w_end and w_start < a_end


def test_validation_failure_stops_run():
    llm = FakeClaude()
    events = collect_events(fake_services(llm), "ZZZZQX")
    errors = [e for e in events if e.event == "error"]
    assert len(errors) == 1 and errors[0].data == {"stage": "validate", "message": "ticker not found", "terminal": True}
    assert not any(e.event == "report" for e in events) and llm.calls == []


def test_risk_failure_degrades_section():
    events = collect_events(fake_services(FakeClaude({"risk": [LlmError("refusal", "model declined the request")]})))
    report = report_from_event(events[-1])
    assert isinstance(report.risks, StageError) and "declined" in report.risks.message
    assert report.signal in {"BUY", "HOLD", "SELL"}
    assert any(e.event == "error" and e.data["stage"] == "risk" and not e.data["terminal"] for e in events)


def test_analyst_failure_keeps_preliminary_signal():
    events = collect_events(fake_services(FakeClaude({"analyst": [LlmError("timeout", "analyst call timed out")]})))
    report = report_from_event(events[-1])
    assert isinstance(report.analyst, StageError) and "not reviewed" in report.analyst.message
    assert report.signal == report.scorecard.preliminary_signal and report.signal_reviewed is False


def test_writer_failure_degrades_narrative():
    report = report_from_event(collect_events(fake_services(FakeClaude(markdown=LlmError("api", "boom"))))[-1])
    assert isinstance(report.narrative, StageError) and isinstance(report.analyst, AnalystView)


def test_comps_reask_then_success():
    first = PeerPicks(peers=[PeerPick(ticker=t, name=t) for t in ("MSFT", "ZZZZQX", "YYYYQX")])
    llm = FakeClaude({"comps": [first]})  # second proposal falls back to the default (4 valid peers)
    report = report_from_event(collect_events(fake_services(llm))[-1])
    assert isinstance(report.comps, CompsTable) and len(report.comps.peers) == 4
    assert llm.agents_called().count("comps") == 3  # pick, re-ask, explain
    comps_calls = [user for agent, user in llm.calls if agent == "comps"]
    assert '"rejected_peers"' not in comps_calls[0] and '"rejected_peers"' in comps_calls[1]


def test_static_fallback_when_agent_cannot_help(monkeypatch):
    monkeypatch.setitem(PEERS_FALLBACK, "Technology", ["MSFT", "GOOGL", "DELL", "HPQ"])  # peers with recorded data
    bad = PeerPicks(peers=[PeerPick(ticker=t, name=t) for t in ("ZZZZQX", "YYYYQX", "XXXXQX")])
    report = report_from_event(collect_events(fake_services(FakeClaude({"comps": [bad, bad]})))[-1])
    assert isinstance(report.comps, CompsTable)
    assert "fallback" in report.comps.peer_origin.values()
    assert any("static sector peers" in w for w in report.quality_warnings)


def test_comps_agent_runs_without_search_results():
    data = DataLayer.recorded()
    data.search.source.search = lambda *a, **k: {"results": []}  # type: ignore[method-assign]
    llm = FakeClaude()
    report = report_from_event(collect_events(fake_services(llm, data))[-1])
    assert isinstance(report.comps, CompsTable) and "comps" in llm.agents_called()


def test_cached_report_within_an_hour_makes_no_calls():
    svc = fake_services(FakeClaude())
    collect_events(svc)
    llm = FakeClaude()
    svc.llm = llm
    events = collect_events(svc)
    assert events[-1].event == "report" and events[-1].data["from_cache"] is True and llm.calls == []


def test_warm_agent_caches_leave_only_analyst_and_writer():
    svc = fake_services(FakeClaude())
    collect_events(svc)
    svc.data.cache.delete("report:AAPL")
    llm = FakeClaude()
    svc.llm = llm
    report = report_from_event(collect_events(svc)[-1])
    assert sorted(llm.agents_called()) == ["analyst", "writer"]
    assert "peers:AAPL:claude-opus-5-5" in report.cache_hits and any(k.startswith("riskreport:") for k in report.cache_hits)


def test_refresh_bypasses_report_and_peer_caches():
    svc = fake_services(FakeClaude())
    collect_events(svc)
    llm = FakeClaude()
    svc.llm = llm
    collect_events(svc, refresh=True)
    assert "comps" in llm.agents_called() and "risk" not in llm.agents_called()  # risk selection keyed by filing


class SlowFilings(FixtureFilingSource):
    def latest_annual(self, ticker):
        time.sleep(2)
        return super().latest_annual(ticker)


def test_blocking_fetch_does_not_delay_other_branches():
    data = DataLayer.recorded()
    data.sec = SecData(data.cache, SlowFilings())
    events = collect_events(fake_services(FakeClaude(), data))
    financial = next(i for i, e in enumerate(events) if e.event == "partial" and e.data["key"] == "financials")
    risk_done = next(i for i, e in enumerate(events) if e.event == "stage" and e.data["stage"] == "risk" and e.data["status"] == "done")
    assert financial < risk_done


@pytest.mark.parametrize("ticker", ["NVDA", "JPM", "COST", "TSLA"])
def test_all_fixture_tickers_produce_reports(ticker):
    report = report_from_event(collect_events(fake_services(FakeClaude()), ticker)[-1])
    assert isinstance(report.comps, CompsTable) and len(report.comps.peers) >= 3
    assert isinstance(report.risks, RiskReport) and len(report.risks.risks) == 6
    if ticker == "JPM":
        assert report.comps.metric_set == "financials" and "ev_ebitda" not in report.comps.metrics


def test_stage_failed_usages_are_recorded():
    events = collect_events(fake_services(FakeClaude({"risk": [LlmError("api", "boom")]})))
    report = report_from_event(events[-1])
    assert any(u.agent == "risk" and u.error for u in report.llm_usage)


def test_rationales_come_from_explain_call_with_peer_summaries():
    llm = FakeClaude()
    report = report_from_event(collect_events(fake_services(llm))[-1])
    assert isinstance(report.comps, CompsTable)
    explain = json.loads(next(user for agent, user in llm.calls if agent == "comps" and '"peers"' in user))
    assert [p["ticker"] for p in explain["peers"]] == [r.ticker for r in report.comps.peers]
    assert all(p["business_summary"] for p in explain["peers"])
    assert set(report.comps.peer_rationales) == {r.ticker for r in report.comps.peers}


def test_explain_failure_keeps_table_without_rationales():
    llm = FakeClaude({"comps": [PeerPicks(peers=[PeerPick(ticker=t, name=t) for t in ("MSFT", "GOOGL", "DELL", "HPQ")]),
                                LlmError("refusal", "model declined the request")]})
    report = report_from_event(collect_events(fake_services(llm))[-1])
    assert isinstance(report.comps, CompsTable) and len(report.comps.peers) == 4
    assert report.comps.peer_rationales == {}
    assert any("peer rationales unavailable" in w for w in report.quality_warnings)


class SlowExplain(FakeClaude):
    """Delays only the explain call, so its effect on event order is visible."""

    async def parse(self, agent, output_model, system, user):
        if '"peers"' in user:
            await asyncio.sleep(0.5)
        return await super().parse(agent, output_model, system, user)


def comps_partials(events):
    return [(i, e.data["value"]) for i, e in enumerate(events) if e.event == "partial" and e.data["key"] == "comps"]


def test_comps_emitted_before_rationales_and_not_awaited_by_scorecard():
    events = collect_events(fake_services(SlowExplain()))
    (first_i, first), (second_i, second) = comps_partials(events)
    assert first["peer_rationales"] == {} and set(second["peer_rationales"]) == {r["ticker"] for r in first["rows"][1:]}
    scorecard_i = next(i for i, e in enumerate(events) if e.event == "partial" and e.data["key"] == "scorecard")
    assert first_i < scorecard_i < second_i
    report = report_from_event(events[-1])
    assert isinstance(report.comps, CompsTable) and report.comps.peer_rationales == second["peer_rationales"]
    assert "comps_explain" in report.timings_ms


def test_cached_peers_emit_one_comps_partial_with_rationales():
    svc = fake_services(FakeClaude())
    collect_events(svc)
    svc.data.cache.delete("report:AAPL")
    events = collect_events(svc)
    partials = comps_partials(events)
    assert len(partials) == 1 and partials[0][1]["peer_rationales"]


def test_failed_explain_is_not_cached():
    svc = fake_services(FakeClaude({"comps": [PeerPicks(peers=[PeerPick(ticker=t, name=t) for t in ("MSFT", "GOOGL", "DELL", "HPQ")]),
                                         LlmError("timeout", "comps call timed out")]}))
    collect_events(svc)
    assert svc.data.cache.get("peers:AAPL:claude-opus-5-5", PeerChoice) is None


def test_validation_reason_survives_message_rewording(monkeypatch):
    from equity_agent.data.market import DataError

    monkeypatch.setattr(DataError, "__str__", lambda self: "reworded message")
    errors = [e for e in collect_events(fake_services(FakeClaude()), "ZZZZQX") if e.event == "error"]
    assert errors[0].data["message"] == "ticker not found"


def test_writer_failure_is_recorded_once():
    report = report_from_event(collect_events(fake_services(FakeClaude(markdown=LlmError("api", "boom"))))[-1])
    assert isinstance(report.narrative, StageError) and report.narrative.message == "boom"
    assert [u.agent for u in report.llm_usage].count("writer") == 1


def test_cached_report_identity_mismatch_is_discarded():
    from equity_agent.models import ResearchReport
    from equity_agent.pipeline import cached_report
    services = fake_services()
    try:
        report = report_from_event(collect_events(services)[-1])
        services.data.cache.set("report:FRHC_KZ", report, ResearchReport, 60)
        assert cached_report(services.data.cache, "FRHC_KZ") is None
        assert services.data.cache.get_raw("report:FRHC_KZ") is None
        corrupted = report.model_copy(deep=True)
        corrupted.financials.snapshot.ticker = "MSFT"
        services.data.cache.set("report:AAPL", corrupted, ResearchReport, 60)
        assert cached_report(services.data.cache, "AAPL") is None
    finally:
        services.data.close()


def test_legacy_report_remains_readable_but_native_history_is_rejected():
    from equity_agent.models import QuoteProvenance, ResearchReport
    from equity_agent.pipeline import cached_report
    services = fake_services()
    try:
        report = report_from_event(collect_events(services)[-1])
        report.financials.snapshot.quote_provenance = None
        report.financials.financial_currency = None
        services.data.cache.set("report:AAPL", report, ResearchReport, 60)
        assert cached_report(services.data.cache, "AAPL") is not None
        report.ticker = report.financials.snapshot.ticker = "FRHC_KZ"
        report.financials.snapshot.week52_low = report.financials.snapshot.week52_high = None
        report.financials.snapshot.quote_provenance = QuoteProvenance(
            provider="KASE", exchange="KASE", source_symbol="FRHC_KZ", source_url="https://kase.kz/api/instruments/securities/FRHC_KZ/")
        assert isinstance(report.comps, CompsTable)
        report.comps.target.ticker = "FRHC_KZ"
        services.data.cache.set("report:FRHC_KZ", report, ResearchReport, 60)
        assert cached_report(services.data.cache, "FRHC_KZ") is None
        report.financials.price_history = []
        services.data.cache.set("report:FRHC_KZ", report, ResearchReport, 60)
        assert cached_report(services.data.cache, "FRHC_KZ") is not None
    finally:
        services.data.close()


def test_bad_history_date_degrades_only_history(monkeypatch):
    services = fake_services()
    monkeypatch.setattr(services.data.market.source, "income", lambda ticker: {"Total Revenue": {"bad-date": 10}})
    try:
        report = report_from_event(collect_events(services)[-1])
        assert report.financials.snapshot.price > 0 and not report.financials.revenue_history
        assert any("financial history unavailable" in warning for warning in report.quality_warnings)
    finally:
        services.data.close()


def test_writer_failure_after_delta_keeps_partial_text_and_usage_once():
    import time
    class PartialWriter(FakeClaude):
        async def stream(self, agent, system, user, on_usage):
            yield "## Company overview\nPartial text."
            usage = self._usage(agent, time.perf_counter(), error="fixture stream failure")
            on_usage(usage)
            raise LlmError("connection", "fixture stream failure", usage)
    services = fake_services(PartialWriter())
    try:
        events = collect_events(services)
        report = report_from_event(events[-1])
        assert any(event.event == "narrative" for event in events)
        assert isinstance(report.narrative, StageError)
        assert report.narrative_markdown.endswith("Partial text.")
        assert len([usage for usage in report.llm_usage if usage.agent == "writer"]) == 1
    finally:
        services.data.close()


def test_composite_lookups_report_every_cache_key():
    data = DataLayer.recorded()
    data.market.peers(["MSFT", "GOOGL"])
    warm = data.sec.risk_headings("AAPL").value
    report = report_from_event(collect_events(fake_services(FakeClaude(), data))[-1])
    accession = warm.filing.accession_no  # type: ignore[union-attr]
    assert {"quote:MSFT", "quote:GOOGL", "filing:AAPL", f"risk:{accession}"} <= set(report.cache_hits)


def test_unknown_ticker_raises_run_failed_without_spending():
    from equity_agent.pipeline import RunFailed, run_report

    llm = FakeClaude()
    data = DataLayer.recorded()
    searches = []
    data.search.source.search = lambda *a, **k: searches.append(a) or {"results": []}  # type: ignore[method-assign]
    with pytest.raises(RunFailed) as caught:
        asyncio.run(run_report(fake_services(llm, data), "ZZZZQX"))
    assert (caught.value.stage, caught.value.reason) == ("validate", "ticker not found")
    assert llm.calls == [] and searches == []


def test_cli_and_evaluation_paths_give_the_same_report(capsys):
    from equity_agent import cli
    from equity_agent.pipeline import clear_agent_caches, run_report

    volatile = {"generated_at", "timings_ms", "llm_usage"}
    assert asyncio.run(cli.run("COST", as_json=True, refresh=False, services=fake_services(FakeClaude()))) == 0
    from_cli = json.loads(capsys.readouterr().out)
    svc = fake_services(FakeClaude())
    clear_agent_caches(svc.data.cache, "COST")
    from_eval = asyncio.run(run_report(svc, "COST")).model_dump(mode="json")
    assert {k: v for k, v in from_cli.items() if k not in volatile} == {k: v for k, v in from_eval.items() if k not in volatile}


def test_agent_cache_keys_name_the_configured_model():
    from equity_agent.config import AgentConfig, AgentName
    from equity_agent.pipeline import _default_models

    models: dict[AgentName, AgentConfig] = {**_default_models(), "comps": AgentConfig(model="claude-sonnet-5-5", effort="low")}
    svc = Services(data=DataLayer.recorded(), llm=FakeClaude(), models=models)
    collect_events(svc)
    assert svc.data.cache.get("peers:AAPL:claude-sonnet-5-5", PeerChoice) is not None
    assert svc.data.cache.get("peers:AAPL:default", PeerChoice) is None


def test_peer_choice_round_trips_through_a_table():
    report = report_from_event(collect_events(fake_services(FakeClaude()))[-1])
    assert isinstance(report.comps, CompsTable)
    choice = PeerChoice.from_table(report.comps)
    assert choice.tickers == [r.ticker for r in report.comps.peers]
    assert choice.table_kwargs() == {"rationales": report.comps.peer_rationales, "origin": report.comps.peer_origin, "sources": report.comps.sources}


def test_stage_cached_flags_are_per_stage():
    data = DataLayer.recorded()
    data.sec.risk_headings("AAPL")  # warm only the risk branch's data
    events = collect_events(fake_services(FakeClaude(), data))
    done = {e.data["stage"]: e.data.get("cached") for e in events if e.event == "stage" and e.data["status"] == "done"}
    assert done["financials"] is False and done["news"] is False
