"""Regression coverage for provider outages, fallback selection, refresh and shutdown ownership."""

import asyncio
import threading
from unittest.mock import Mock

import pytest
from edgar.exceptions import CompanyNotFoundError
from fakes import FakeClaude, collect_events, fake_services

from equity_agent.agents.agents import PEERS_FALLBACK
from equity_agent.data import DataLayer
from equity_agent.data import sec as sec_module
from equity_agent.data.sec import EdgarSource, SecData
from equity_agent.models import CompsTable, PeerChoice, PeerPick, PeerPicks, RiskReport, RiskSelection, Unavailable
from equity_agent.pipeline import cached_report, report_from_event
from equity_agent.streaming import RunRegistry


def test_cached_report_needs_no_provider_access(monkeypatch):
    services = fake_services()
    original = report_from_event(collect_events(services)[-1])
    services.data.cache.delete("quote:AAPL")
    unavailable = Mock(side_effect=ConnectionError("Yahoo is offline"))
    monkeypatch.setattr(services.data.market.source, "info", unavailable)
    try:
        events = collect_events(services, " aapl ")
        assert events[-1].data["from_cache"] is True
        assert report_from_event(events[-1]) == original
        unavailable.assert_not_called()
    finally:
        services.data.close()


def test_sec_outage_is_not_cached_as_a_missing_filing(monkeypatch):
    recovered = Mock()
    recovered.get_filings.return_value.latest.return_value = None
    company = Mock(side_effect=[ConnectionError("SEC is offline"), recovered])
    monkeypatch.setattr(sec_module, "Company", company)
    data = DataLayer.recorded()
    sec = SecData(data.cache, EdgarSource("Test t@example.com"))
    try:
        with pytest.raises(ConnectionError):
            sec.latest_filing("AAPL")
        assert data.cache.get_raw("filing:AAPL") is None
        assert isinstance(sec.latest_filing("AAPL").value, Unavailable)
        assert sec.latest_filing("AAPL").hit
        assert company.call_count == 2
    finally:
        data.close()


def test_sec_unknown_company_remains_a_reasoned_absence(monkeypatch):
    monkeypatch.setattr(sec_module, "Company", Mock(side_effect=CompanyNotFoundError("UNKNOWN")))
    assert EdgarSource("Test t@example.com").latest_annual("UNKNOWN") is None


def test_refresh_discovers_a_new_filing_and_runs_its_risk_selection(monkeypatch):
    services = fake_services()
    first = report_from_event(collect_events(services)[-1])
    assert isinstance(first.risks, RiskReport)
    new_filing = first.risks.filing.model_copy(update={"accession_no": "new-annual-filing"})
    lookup = Mock(return_value=new_filing)
    monkeypatch.setattr(services.data.sec.source, "latest_annual", lookup)
    services.llm = llm = FakeClaude()
    try:
        second = report_from_event(collect_events(services, refresh=True)[-1])
        assert isinstance(second.risks, RiskReport)
        assert second.risks.filing.accession_no == "new-annual-filing"
        lookup.assert_called_once_with("AAPL")
        assert llm.agents_called().count("risk") == 1
        # A refresh of the unchanged accession reuses its immutable content and selection.
        services.llm = llm = FakeClaude()
        collect_events(services, refresh=True)
        assert "risk" not in llm.agents_called()
    finally:
        services.data.close()


def test_fallback_considers_valid_candidates_after_the_worker_limit(monkeypatch):
    monkeypatch.setitem(PEERS_FALLBACK, "Technology", ["ZZZZQX", "YYYYQX", "XXXXQX", "MSFT", "GOOGL", "DELL"])
    bad = PeerPicks(peers=[PeerPick(ticker=t, name=t) for t in ("ZZZZQX", "YYYYQX", "XXXXQX")])
    services = fake_services(FakeClaude({"comps": [bad, bad]}))
    try:
        report = report_from_event(collect_events(services)[-1])
        assert isinstance(report.comps, CompsTable)
        assert [p.ticker for p in report.comps.peers] == ["MSFT", "GOOGL", "DELL"]
    finally:
        services.data.close()


def test_invalid_persisted_risk_selection_is_replaced():
    services = fake_services()
    first = report_from_event(collect_events(services)[-1])
    assert isinstance(first.risks, RiskReport)
    key = f"riskreport:{first.risks.filing.accession_no}:{services.models['risk'].model}"
    services.data.cache.set(key, RiskSelection(risks=[first.risks.risks[0]] * 6), RiskSelection, None)
    services.data.cache.delete("report:AAPL")
    services.llm = llm = FakeClaude()
    try:
        report = report_from_event(collect_events(services)[-1])
        assert isinstance(report.risks, RiskReport)
        assert len({r.source_heading for r in report.risks.risks}) == 6
        assert llm.agents_called().count("risk") == 1
        assert key not in report.cache_hits
        stored = services.data.cache.get(key, RiskSelection)
        assert isinstance(stored, RiskSelection)
        assert len({r.source_heading for r in stored.risks}) == 6
    finally:
        services.data.close()


def test_cached_peers_that_lost_eligibility_are_reselected():
    services = fake_services()
    collect_events(services)
    key = f"peers:AAPL:{services.models['comps'].model}"
    services.data.cache.set(key, PeerChoice(tickers=["MSFT", "GOOGL", "ZZZZQX"]), PeerChoice, None)
    services.data.cache.delete("report:AAPL")
    services.llm = llm = FakeClaude()
    try:
        report = report_from_event(collect_events(services)[-1])
        assert isinstance(report.comps, CompsTable)
        assert len(report.comps.peers) >= 3
        assert all(p.ticker != "ZZZZQX" for p in report.comps.peers)
        assert llm.agents_called().count("comps") == 2  # pick and explain
        assert key not in report.cache_hits
        choice = services.data.cache.get(key, PeerChoice)
        assert isinstance(choice, PeerChoice) and "ZZZZQX" not in choice.tickers
    finally:
        services.data.close()


def test_shutdown_cancels_active_model_work_without_finishing_the_report():
    class BlockedClaude(FakeClaude):
        def __init__(self):
            super().__init__()
            self.started = asyncio.Event()
            self.cancelled: list[str] = []

        async def parse(self, agent, output_model, system, user):
            self.started.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled.append(agent)
            return await super().parse(agent, output_model, system, user)

    async def scenario():
        llm = BlockedClaude()
        services = fake_services(llm)
        registry = RunRegistry(services)
        events = registry.subscribe("AAPL")
        try:
            await asyncio.wait_for(llm.started.wait(), 5)
            await asyncio.wait_for(registry.close(), 2)
            assert llm.cancelled
            assert cached_report(services.data.cache, "AAPL") is None
            assert not registry._tasks
            assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
        finally:
            await events.aclose()  # type: ignore[attr-defined]
            await registry.close()
            services.data.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("repeat_close", [False, True])
def test_shutdown_drains_blocking_calls_before_services_close(monkeypatch, repeat_close):
    async def scenario():
        services = fake_services()
        loop = asyncio.get_running_loop()
        started = asyncio.Event()
        release = threading.Event()
        original = services.data.market.source.income

        def blocked_income(ticker):
            loop.call_soon_threadsafe(started.set)
            if not release.wait(5):
                raise TimeoutError("test did not release provider call")
            return original(ticker)

        monkeypatch.setattr(services.data.market.source, "income", blocked_income)
        registry = RunRegistry(services)
        events = registry.subscribe("AAPL")
        closers = []
        try:
            await asyncio.wait_for(started.wait(), 5)
            closers.append(asyncio.create_task(registry.close()))
            if repeat_close:
                closers.append(asyncio.create_task(registry.close()))
            for _ in range(20):
                await asyncio.sleep(0)
            assert all(not task.done() for task in closers), "shutdown returned while a provider still owned the cache"
            release.set()
            await asyncio.wait_for(asyncio.gather(*closers), 2)
            assert services.data.cache.get_raw("fin:AAPL") is not None
            assert cached_report(services.data.cache, "AAPL") is None
        finally:
            release.set()
            await asyncio.gather(*closers, return_exceptions=True)
            await events.aclose()  # type: ignore[attr-defined]
            await registry.close()
            services.data.close()

    asyncio.run(scenario())


def test_closed_registry_rejects_new_runs():
    async def scenario():
        services = fake_services()
        registry = RunRegistry(services)
        try:
            await registry.close()
            with pytest.raises(RuntimeError, match="closed"):
                registry.subscribe("AAPL")
            assert registry.started == 0
        finally:
            services.data.close()

    asyncio.run(scenario())
