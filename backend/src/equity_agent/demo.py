"""The offline demo: record live runs whole, then replay them through the real pipeline without any network.

A recording (`backend/demo/<T>/`) is one live run per ticker: every provider response, in the fixture layout that
`DataLayer.recorded` reads, plus `agents.json` with each agent's validated answer and the Writer's text. Data and
answers come from the same run, so a replay shows the same peers, risks and signal. `evaluate --record` writes it;
`DEMO_OFFLINE=1` serves it. It is kept apart from `tests/fixtures/`, so refreshing it never changes test results.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from equity_agent.cache import Cache
from equity_agent.config import BACKEND_ROOT, AgentName, Settings
from equity_agent.data import DataError, DataLayer, MarketData, SearchData, SecData
from equity_agent.data.fixtures import FixtureFilingSource, FixtureMarketSource, FixtureSearchSource
from equity_agent.data.market import QUOTE_FIELDS, MarketSource
from equity_agent.data.search import SearchSource, Topic
from equity_agent.data.sec import FilingSource
from equity_agent.llm import LlmClient, LlmError
from equity_agent.models import Fetched, FilingRef, LlmUsage, Quote
from equity_agent.pipeline import Services

T = TypeVar("T", bound=BaseModel)

DEMO_DIR = BACKEND_ROOT / "demo"
AGENTS_FILE = "agents.json"
WRITER_CHUNK = 24  # characters per replayed Writer fragment


class NotRecorded(DataError):
    reason = "not available offline"


# ---- provider data in the fixture layout (also used by scripts/record_fixtures.py) ------------------------------


def write_fixture(directory: Path, ticker: str, name: str, data: Any) -> Path:
    folder = directory / ticker
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    text = data if isinstance(data, str) else json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True)
    path.write_text(text, encoding="utf-8")
    return path


def quote_subset(info: dict[str, Any]) -> dict[str, Any]:
    """The provider fields the quote parser reads; the rest of Yahoo's payload is noise."""
    return {k: info.get(k) for k in QUOTE_FIELDS if info.get(k) is not None}


def trimmed_search(response: dict[str, Any]) -> dict[str, Any]:
    return {"query": response.get("query"), "results": response.get("results", [])}


def search_file(topic: Topic) -> str:
    return "search_news.json" if topic == "news" else "search_competitors.json"


# ---- recording ----------------------------------------------------------------------------------------------------


class Recording:
    """Where a recording goes and which target ticker is being recorded (searches and answers are filed under it)."""

    def __init__(self, directory: Path = DEMO_DIR) -> None:
        self.directory = directory
        self.target = ""
        self.answers: list[dict[str, Any]] = []
        self.writer: dict[str, Any] | None = None

    def start(self, ticker: str) -> None:
        """Begin a target: its old answers go, so nothing stale is replayed. Its data files are overwritten as the run
        fetches them; they stay otherwise, because an earlier target in the same run may have recorded them as a peer."""
        (self.directory / ticker / AGENTS_FILE).unlink(missing_ok=True)
        self.target, self.answers, self.writer = ticker, [], None

    def save(self) -> None:
        if self.answers or self.writer:
            write_fixture(self.directory, self.target, AGENTS_FILE, {"answers": self.answers, "writer": self.writer})


class RecordingMarketSource:
    def __init__(self, inner: MarketSource, recording: Recording) -> None:
        self.inner, self.recording = inner, recording

    def info(self, ticker: str) -> dict[str, Any]:
        info = self.inner.info(ticker)
        write_fixture(self.recording.directory, ticker, "info.json", quote_subset(info))
        return info

    def income(self, ticker: str) -> dict[str, dict[str, float | None]]:
        rows = self.inner.income(ticker)
        write_fixture(self.recording.directory, ticker, "income.json", rows)
        return rows

    def closes(self, ticker: str) -> list[tuple[str, float]]:
        closes = self.inner.closes(ticker)
        write_fixture(self.recording.directory, ticker, "closes.json", closes)
        return closes


class RecordingFilingSource:
    def __init__(self, inner: FilingSource, recording: Recording) -> None:
        self.inner, self.recording = inner, recording

    def latest_annual(self, ticker: str) -> FilingRef | None:
        ref = self.inner.latest_annual(ticker)
        if ref is not None:
            write_fixture(self.recording.directory, ticker, "filing.json", ref.model_dump(mode="json"))
        return ref

    def risk_text(self, ref: FilingRef) -> str | None:
        text = self.inner.risk_text(ref)
        write_fixture(self.recording.directory, ref.ticker, "risk_text.txt", text or "")
        return text


class RecordingSearchSource:
    def __init__(self, inner: SearchSource, recording: Recording) -> None:
        self.inner, self.recording = inner, recording

    def search(self, query: str, *, topic: Topic, days: int | None) -> dict[str, Any]:
        response = self.inner.search(query, topic=topic, days=days)
        write_fixture(self.recording.directory, self.recording.target, search_file(topic), trimmed_search(response))
        return response


class RecordingClient:
    """Passes calls to a real client and keeps each validated answer and the Writer's text, with their latency."""

    def __init__(self, inner: LlmClient, recording: Recording) -> None:
        self.inner, self.recording = inner, recording

    async def parse(self, agent: AgentName, output_model: type[T], system: str, user: str) -> tuple[T, LlmUsage]:
        output, usage = await self.inner.parse(agent, output_model, system, user)
        self.recording.answers.append(
            {"agent": agent, "type": output_model.__name__, "output": output.model_dump(mode="json"), **_usage_fields(usage)}
        )
        return output, usage

    async def stream(
        self, agent: AgentName, system: str, user: str, on_usage: Callable[[LlmUsage], None]
    ) -> AsyncIterator[str]:
        chunks: list[str] = []
        usages: list[LlmUsage] = []

        def keep(usage: LlmUsage) -> None:
            usages.append(usage)
            on_usage(usage)

        async for text in self.inner.stream(agent, system, user, keep):
            chunks.append(text)
            yield text
        if usages and usages[-1].error is None:
            self.recording.writer = {"markdown": "".join(chunks), **_usage_fields(usages[-1])}

    async def warm(self) -> None:
        await self.inner.warm()

    async def close(self) -> None:
        await self.inner.close()


def _usage_fields(usage: LlmUsage) -> dict[str, Any]:
    return {"model": usage.model, "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens, "ms": usage.ms}


# ---- replay -------------------------------------------------------------------------------------------------------


def payload_ticker(user: str) -> str:
    """The target ticker of an agent's input (every agent's payload names it)."""
    payload = json.loads(user.split("\n\nYour previous answer")[0])
    ticker = payload.get("ticker") or (payload.get("company") or {}).get("ticker")
    if not isinstance(ticker, str):
        raise ValueError("agent input names no ticker")
    return ticker


class ReplayClaude:
    """An LlmClient that answers from a recording, taking `speed` × the recorded time and costing nothing.

    Answers are looked up by ticker and output type, in recorded order (a re-ask replays the second answer), and wrap
    around so a refreshed run replays the same sequence.
    """

    def __init__(self, directory: Path = DEMO_DIR, speed: float = 0.4) -> None:
        self.directory = directory
        self.speed = speed
        self._recordings: dict[str, dict[str, Any]] = {}
        self._cursor: dict[tuple[str, str], int] = {}

    def _recording(self, ticker: str) -> dict[str, Any]:
        if ticker not in self._recordings:
            path = self.directory / ticker / AGENTS_FILE
            self._recordings[ticker] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return self._recordings[ticker]

    def _usage(self, agent: AgentName, record: dict[str, Any], start: float) -> LlmUsage:
        return LlmUsage(
            agent=agent,
            model=record["model"],
            input_tokens=record["input_tokens"],
            output_tokens=record["output_tokens"],
            ms=int((time.perf_counter() - start) * 1000),
            cost_usd=0.0,
        )

    async def parse(self, agent: AgentName, output_model: type[T], system: str, user: str) -> tuple[T, LlmUsage]:
        start = time.perf_counter()
        ticker = payload_ticker(user)
        name = output_model.__name__
        answers = [a for a in self._recording(ticker).get("answers", []) if a["type"] == name]
        if not answers:
            raise LlmError("api", f"no recorded {name} answer for {ticker} offline")
        index = self._cursor.get((ticker, name), 0)
        self._cursor[(ticker, name)] = index + 1
        record = answers[index % len(answers)]
        await asyncio.sleep(record["ms"] / 1000 * self.speed)
        output = output_model.model_validate(record["output"])
        return output, self._usage(agent, record, start)

    async def stream(
        self, agent: AgentName, system: str, user: str, on_usage: Callable[[LlmUsage], None]
    ) -> AsyncIterator[str]:
        start = time.perf_counter()
        ticker = payload_ticker(user)
        record = self._recording(ticker).get("writer")
        if not record:
            raise LlmError("api", f"no recorded narrative for {ticker} offline")
        text: str = record["markdown"]
        chunks = [text[i : i + WRITER_CHUNK] for i in range(0, len(text), WRITER_CHUNK)] or [""]
        pause = record["ms"] / 1000 * self.speed / len(chunks)
        for chunk in chunks:
            await asyncio.sleep(pause)
            yield chunk
        on_usage(self._usage(agent, record, start))

    async def warm(self) -> None:
        return None

    async def close(self) -> None:
        return None


class OfflineMarketSource(FixtureMarketSource):
    """Recorded market data; a ticker that was never recorded is "not available offline", not "not found"."""

    def info(self, ticker: str) -> dict[str, Any]:
        if not (self.directory / ticker / "info.json").exists():
            raise NotRecorded(ticker)
        return super().info(ticker)


class OfflineMarketData(MarketData):
    """A report needs a recorded run (its agents' answers); a ticker recorded only as someone's peer is not one."""

    def __init__(self, cache: Cache, directory: Path) -> None:
        super().__init__(cache, OfflineMarketSource(directory))
        self.directory = directory

    def quote(self, ticker: str, *, refresh: bool = False) -> Fetched[Quote]:
        if not (self.directory / ticker / AGENTS_FILE).exists():
            raise NotRecorded(ticker)
        return super().quote(ticker, refresh=refresh)


def offline_services(settings: Settings, directory: Path | None = None) -> Services:
    """The demo recording behind the real pipeline: no network, an in-memory cache, replayed agent answers."""
    directory = directory or DEMO_DIR
    cache = Cache(None)
    data = DataLayer(
        cache=cache,
        market=OfflineMarketData(cache, directory),
        sec=SecData(cache, FixtureFilingSource(directory)),
        search=SearchData(cache, FixtureSearchSource(directory)),
    )
    return Services(data=data, llm=ReplayClaude(directory, settings.replay_speed), models=settings.agents)


def recording_services(
    recording: Recording,
    llm: LlmClient,
    *,
    market: MarketSource,
    filings: FilingSource,
    search: SearchSource,
    settings: Settings | None = None,
) -> Services:
    """Sources and a client, each wrapped to record, over a fresh in-memory cache so every call really happens."""
    cache = Cache(None)
    data = DataLayer(
        cache=cache,
        market=MarketData(cache, RecordingMarketSource(market, recording)),
        sec=SecData(cache, RecordingFilingSource(filings, recording)),
        search=SearchData(cache, RecordingSearchSource(search, recording)),
    )
    services = Services(data=data, llm=RecordingClient(llm, recording))
    if settings is not None:
        services.models = settings.agents
    return services
