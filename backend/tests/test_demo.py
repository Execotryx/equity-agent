import asyncio
import json
import socket
from pathlib import Path

import pytest
from fakes import FakeClaude, fake_services, without_worker
from fastapi.testclient import TestClient

from equity_agent import demo
from equity_agent.api import create_app
from equity_agent.config import load_settings
from equity_agent.data.fixtures import FixtureFilingSource, FixtureMarketSource, FixtureSearchSource
from equity_agent.models import CompsTable, ResearchReport, RiskReport
from equity_agent.pipeline import RunFailed, live_services, run_report
from equity_agent.warm import warm_all

ENV = {"ANTHROPIC_API_KEY": "sk-ant-x", "TAVILY_API_KEY": "tvly-x", "EDGAR_IDENTITY": "Test t@example.com"}


def record(directory: Path, tickers: list[str]) -> dict[str, ResearchReport]:
    """Record FakeClaude runs over the test fixtures, the way `evaluate --record` records live runs."""
    recording = demo.Recording(directory)
    reports: dict[str, ResearchReport] = {}
    for ticker in tickers:
        recording.start(ticker)
        services = demo.recording_services(
            recording,
            FakeClaude(),
            market=FixtureMarketSource(),
            filings=FixtureFilingSource(),
            search=FixtureSearchSource(),
        )
        reports[ticker] = asyncio.run(run_report(services, ticker))
        recording.save()
    return reports


@pytest.fixture(scope="module")
def recorded(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, ResearchReport]]:
    directory = tmp_path_factory.mktemp("demo")
    return directory, record(directory, ["AAPL", "JPM"])


def offline_settings(**extra: str):
    return load_settings({**ENV, "DEMO_OFFLINE": "1", "DEMO_REPLAY_SPEED": "0", **extra})


# ---- warm-up ------------------------------------------------------------------------------------------------------


def test_warm_leaves_only_the_analyst_and_writer():
    llm = FakeClaude()
    services = fake_services(llm)
    results = asyncio.run(warm_all(services, ["JPM"]))
    assert [(r.ticker, r.status) for r in results] == [("JPM", "ok")]
    assert set(llm.agents_called()) == {"comps", "risk"}
    assert services.data.cache.get("report:JPM", ResearchReport) is None  # no report is cached
    llm.calls.clear()
    report = asyncio.run(run_report(services, "JPM"))
    assert sorted(llm.agents_called()) == ["analyst", "writer"]  # they run concurrently
    assert "risk:" + report.risks.filing.accession_no in report.cache_hits  # type: ignore[union-attr]


def test_warm_drops_a_cached_report_so_the_demo_streams_live():
    llm = FakeClaude()
    services = fake_services(llm)
    asyncio.run(run_report(services, "AAPL"))
    asyncio.run(warm_all(services, ["AAPL"]))
    llm.calls.clear()
    asyncio.run(run_report(services, "AAPL"))
    assert sorted(llm.agents_called()) == ["analyst", "writer"]


def test_warm_continues_after_an_invalid_ticker():
    results = asyncio.run(warm_all(fake_services(), ["BAD TICKER!", "ZZZZQX", "AAPL"]))
    assert [(r.ticker, r.status) for r in results] == [("BAD TICKER!", "failed"), ("ZZZZQX", "failed"), ("AAPL", "ok")]
    assert results[1].problems == ["ticker not found"]


# ---- record and replay --------------------------------------------------------------------------------------------


def test_recording_holds_data_and_answers(recorded):
    directory, _ = recorded
    files = {p.name for p in (directory / "AAPL").iterdir()}
    assert {"info.json", "income.json", "closes.json", "filing.json", "risk_text.txt", "agents.json"} <= files
    assert {"search_competitors.json", "search_news.json"} <= files
    agents = json.loads((directory / "AAPL" / "agents.json").read_text(encoding="utf-8"))
    assert sorted(a["type"] for a in agents["answers"]) == ["AnalystOutput", "PeerPicks", "PeerRationales", "RiskSelection"]
    assert agents["writer"]["markdown"].startswith("## Company overview")
    assert (directory / "MSFT" / "info.json").exists()  # peers the agent picked are recorded too


def test_replay_matches_the_recorded_run(recorded):
    directory, live = recorded
    for ticker in ("AAPL", "JPM"):
        services = demo.offline_services(offline_settings(), directory)
        replayed = asyncio.run(run_report(services, ticker))
        original = live[ticker]
        assert isinstance(replayed.comps, CompsTable) and isinstance(original.comps, CompsTable)
        assert [r.ticker for r in replayed.comps.rows] == [r.ticker for r in original.comps.rows]
        assert replayed.comps.peer_rationales == original.comps.peer_rationales
        assert isinstance(replayed.risks, RiskReport) and isinstance(original.risks, RiskReport)
        assert [r.title for r in replayed.risks.risks] == [r.title for r in original.risks.risks]
        assert replayed.signal == original.signal
        assert replayed.narrative_markdown == original.narrative_markdown
        assert all(u.cost_usd == 0 for u in replayed.llm_usage)


def test_unrecorded_ticker_is_not_available_offline(recorded):
    directory, _ = recorded
    services = demo.offline_services(offline_settings(), directory)
    with pytest.raises(RunFailed) as failed:
        asyncio.run(run_report(services, "NVDA"))
    assert (failed.value.stage, failed.value.reason) == ("validate", "not available offline")


def test_a_ticker_recorded_only_as_a_peer_is_not_a_report(recorded):
    directory, _ = recorded
    assert (directory / "MSFT" / "info.json").exists() and not (directory / "MSFT" / "agents.json").exists()
    services = demo.offline_services(offline_settings(), directory)
    with pytest.raises(RunFailed) as failed:
        asyncio.run(run_report(services, "MSFT"))
    assert failed.value.reason == "not available offline"


def test_missing_answer_degrades_its_section(recorded, tmp_path):
    directory, _ = recorded
    copy = tmp_path / "demo"
    for name in ("AAPL", "MSFT", "GOOGL", "DELL", "HPQ"):
        if (directory / name).exists():
            (copy / name).mkdir(parents=True)
            for f in (directory / name).iterdir():
                (copy / name / f.name).write_bytes(f.read_bytes())
    agents_path = copy / "AAPL" / "agents.json"
    agents = json.loads(agents_path.read_text(encoding="utf-8"))
    agents["answers"] = [a for a in agents["answers"] if a["type"] != "AnalystOutput"]
    agents_path.write_text(json.dumps(agents), encoding="utf-8")
    report = asyncio.run(run_report(demo.offline_services(offline_settings(), copy), "AAPL"))
    assert report.signal_reviewed is False
    assert "no recorded AnalystOutput answer for AAPL offline" in str(report.analyst)


# ---- offline mode through the API, with the network blocked --------------------------------------------------------


def test_offline_api_streams_a_full_report_without_network(recorded, monkeypatch):
    directory, _ = recorded
    monkeypatch.setattr(demo, "DEMO_DIR", directory)

    # Only loopback is allowed: on Windows every asyncio event loop connects a local socket pair to itself.
    connect, create_connection = socket.socket.connect, socket.create_connection
    attempts: list[object] = []

    def local_only(address: object) -> None:
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "::1", "localhost"):
            attempts.append(address)
            raise OSError(f"network blocked in this test: {address}")

    def guarded_connect(self, address):
        local_only(address)
        return connect(self, address)

    def guarded_create_connection(address, *args, **kwargs):
        local_only(address)
        return create_connection(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
    settings = offline_settings()
    services = without_worker(live_services(settings))
    with TestClient(create_app(settings, services)) as client:
        assert client.get("/api/health").json()["offline"] is True
        body = client.get("/api/research/stream", params={"ticker": "AAPL"}).text
        missing = client.get("/api/research/stream", params={"ticker": "NVDA"}).text
    events = [block.split("\n")[0].removeprefix("event: ") for block in body.strip().split("\n\n")]
    assert events[-1] == "report" and "partial" in events and "narrative" in events
    assert '"not available offline"' in missing
    assert attempts == []


def test_live_services_are_offline_only_when_asked(monkeypatch, tmp_path):
    monkeypatch.setattr(demo, "DEMO_DIR", tmp_path)
    assert isinstance(live_services(offline_settings()).llm, demo.ReplayClaude)
    assert load_settings(ENV).offline is False


def test_health_reports_online_by_default():
    with TestClient(create_app(load_settings(ENV), without_worker(fake_services()))) as client:
        assert client.get("/api/health").json()["offline"] is False


def test_replay_speed_must_be_a_non_negative_number():
    from equity_agent.config import ConfigError

    with pytest.raises(ConfigError, match="DEMO_REPLAY_SPEED"):
        load_settings({**ENV, "DEMO_REPLAY_SPEED": "fast"})
