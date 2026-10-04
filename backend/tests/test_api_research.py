import asyncio
import json
import logging
import threading
import time
from typing import Any

import httpx
import pytest
from fakes import FakeClaude, SlowFilingSource, fake_services, without_worker
from fastapi.testclient import TestClient

from equity_agent.api import create_app
from equity_agent.config import load_settings
from equity_agent.data import DataLayer
from equity_agent.llm import LlmError
from equity_agent.models import ResearchReport
from equity_agent.pipeline import Services, cached_report
from equity_agent.streaming import RunRegistry

ANTHROPIC_KEY = "sk-ant-test-secret-value-123"
SETTINGS = load_settings(
    {"ANTHROPIC_API_KEY": ANTHROPIC_KEY, "TAVILY_API_KEY": "tvly-test-456", "EDGAR_IDENTITY": "Test t@example.com"}
)
Event = tuple[str, dict[str, Any]]


def parse_sse(text: str) -> list[Event]:
    events: list[Event] = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def api(services: Services | None = None) -> TestClient:
    services = without_worker(services or fake_services())
    return TestClient(create_app(SETTINGS, services), raise_server_exceptions=False)


def stream(client: TestClient, ticker: str = "AAPL", **params: Any) -> list[Event]:
    response = client.get("/api/research/stream", params={"ticker": ticker, **params})
    assert response.status_code == 200
    return parse_sse(response.text)


# ---- stream ------------------------------------------------------------------------------------------------------


def test_stream_headers_and_event_order():
    with api() as client:
        response = client.get("/api/research/stream", params={"ticker": "AAPL"})
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    events = parse_sse(response.text)
    names = [name for name, _ in events]
    comps = [i for i, (name, data) in enumerate(events) if name == "partial" and data["key"] == "comps"]
    narrative = [i for i, name in enumerate(names) if name == "narrative"]
    assert comps and narrative and comps[0] < narrative[0]
    assert names.count("report") == 1 and names[-1] == "report"
    assert not [n for n in names if n == "error"]


def test_comps_are_sent_twice_without_then_with_rationales():
    with api() as client:
        events = stream(client)
    comps = [data["value"] for name, data in events if name == "partial" and data["key"] == "comps"]
    assert len(comps) == 2
    assert comps[0]["peer_rationales"] == {}
    assert set(comps[1]["peer_rationales"]) == {row["ticker"] for row in comps[1]["rows"] if not row["is_target"]}


def test_cached_report_short_circuits_without_model_calls():
    llm = FakeClaude()
    with api(fake_services(llm)) as client:
        stream(client)
        calls = len(llm.calls)
        events = stream(client)
    assert len(llm.calls) == calls
    assert [name for name, _ in events] == ["stage", "stage", "report"]
    assert events[-1][1]["from_cache"] is True


def test_unknown_ticker_is_one_terminal_error():
    with api() as client:
        events = stream(client, "ZZZZQX")
    errors = [data for name, data in events if name == "error"]
    assert errors == [{"stage": "validate", "message": "ticker not found", "terminal": True}]
    assert events[-1][0] == "error"


def test_failing_risk_branch_is_a_non_terminal_error():
    llm = FakeClaude({"risk": [LlmError("refusal", "model declined the request")]})
    with api(fake_services(llm)) as client:
        events = stream(client)
    errors = [data for name, data in events if name == "error"]
    assert [(e["stage"], e["terminal"]) for e in errors] == [("risk", False)]
    names = [name for name, _ in events]
    assert names.index("report") > names.index("error") and names[-1] == "report"


def test_gzip_is_not_applied_to_the_stream():
    with api() as client:
        response = client.get("/api/research/stream", params={"ticker": "AAPL"}, headers={"Accept-Encoding": "gzip"})
        assert "content-encoding" not in response.headers
        assert parse_sse(response.text)[-1][0] == "report"
        assert not [m for m in client.app.user_middleware if "GZip" in m.cls.__name__]  # type: ignore[attr-defined]


# ---- cached report and errors --------------------------------------------------------------------------------------


def test_cached_report_endpoint():
    with api() as client:
        assert client.get("/api/research/NVDA").status_code == 404
        stream(client, "nvda")
        response = client.get("/api/research/nvda")
        assert response.status_code == 200
        assert ResearchReport.model_validate(response.json()).ticker == "NVDA"


def test_missing_and_invalid_ticker_errors_are_json():
    with api() as client:
        missing = client.get("/api/research/MSFT")
        invalid = client.get("/api/research/BAD TICKER!")
        no_param = client.get("/api/research/stream")
    assert missing.status_code == 404 and missing.json() == {"message": "no cached report for MSFT"}
    assert invalid.status_code == 400 and invalid.json() == {"message": "invalid ticker"}
    assert no_param.status_code == 422 and no_param.json()["message"].startswith("invalid request: ticker")


# ---- lifespan ----------------------------------------------------------------------------------------------------


def test_lifespan_starts_and_stops_resources_in_order():
    services = without_worker(fake_services())
    order: list[str] = []
    start_parser = services.data.sec.start_parser

    def record(name: str, result: Any = None) -> Any:
        def call() -> Any:
            order.append(name)
            return result() if callable(result) else result

        return call

    async def warm() -> None:
        order.append("warm")

    async def close() -> None:
        order.append("llm.close")

    setattr(services.data.sec, "start_parser", record("start_parser", start_parser))
    setattr(services.data, "close", record("data.close"))
    setattr(services.llm, "warm", warm)
    setattr(services.llm, "close", close)
    with TestClient(create_app(SETTINGS, services)):
        assert order == ["start_parser", "warm"]
    assert order == ["start_parser", "warm", "data.close", "llm.close"]


def test_failing_warm_logs_a_redacted_warning_and_starts(caplog):
    services = without_worker(fake_services())

    async def warm() -> None:
        raise RuntimeError(f"rejected key {ANTHROPIC_KEY}")

    setattr(services.llm, "warm", warm)
    with caplog.at_level(logging.WARNING), TestClient(create_app(SETTINGS, services)) as client:
        assert client.get("/api/health").status_code == 200
    assert "Claude warm-up failed" in caplog.text
    assert ANTHROPIC_KEY not in caplog.text and "***" in caplog.text


def test_health_answers_quickly_while_the_worker_parses():
    data = DataLayer.recorded()
    data.sec.source = SlowFilingSource(seconds=4)
    services = fake_services(data=data)
    with TestClient(create_app(SETTINGS, services)) as client:  # real worker: startup loads edgartools in it
        assert services.data.sec.parser_running
        run = threading.Thread(target=lambda: client.get("/api/research/stream", params={"ticker": "AAPL"}))
        run.start()
        time.sleep(1)  # validation done; the risk branch is parsing in the worker
        for _ in range(3):
            started = time.perf_counter()
            assert client.get("/api/health").status_code == 200
            assert time.perf_counter() - started < 1
            time.sleep(0.5)
        run.join(timeout=30)
        assert client.get("/api/research/AAPL").status_code == 200


# ---- run registry ------------------------------------------------------------------------------------------------


def test_concurrent_requests_share_one_run():
    llm = FakeClaude(delay=0.2)
    services = without_worker(fake_services(llm))
    app = create_app(SETTINGS, services)

    async def go() -> tuple[list[Event], list[Event]]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:

            async def get(delay: float) -> list[Event]:
                await asyncio.sleep(delay)
                response = await client.get("/api/research/stream", params={"ticker": "COST"})
                return parse_sse(response.text)

            return await asyncio.gather(get(0), get(0.3))

    first, second = asyncio.run(go())
    assert app.state.registry.started == 1
    assert first == second and first[-1][0] == "report"
    assert llm.agents_called().count("writer") == 1


def test_disconnect_does_not_cancel_the_run():
    services = fake_services(FakeClaude(delay=0.1))
    registry = RunRegistry(services)

    async def go() -> None:
        events = registry.subscribe("JPM")
        async for _ in events:
            break  # the client goes away after the first event
        await events.aclose()  # type: ignore[attr-defined]
        await registry.wait_idle()

    asyncio.run(go())
    report = cached_report(services.data.cache, "JPM")
    assert report is not None and report.ticker == "JPM"


def test_runs_end_and_free_their_slot():
    services = fake_services()
    registry = RunRegistry(services)

    async def go() -> list[str]:
        names = [event.event async for event in registry.subscribe("AAPL")]
        await registry.wait_idle()
        names += [event.event async for event in registry.subscribe("AAPL")]  # a new run: served from the cache
        return names

    names = asyncio.run(go())
    assert names.count("report") == 2 and registry.started == 2
    assert not registry._runs  # noqa: SLF001


@pytest.mark.parametrize("ticker", ["ZZZZQX", "BAD TICKER!"])
def test_invalid_tickers_still_end_their_stream(ticker):
    registry = RunRegistry(fake_services())

    async def go() -> list[str]:
        return [event.event async for event in registry.subscribe(ticker)]

    assert asyncio.run(go())[-1] == "error"
