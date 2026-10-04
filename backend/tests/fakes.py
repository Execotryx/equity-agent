"""FakeClaude: an offline LlmClient. By default it derives valid answers from each agent's input; tests can script
specific outputs or failures per agent, add latency, and inspect the calls that were made."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable
from concurrent.futures import Future
from typing import Any

from pydantic import BaseModel

from equity_agent.config import AgentName
from equity_agent.data import DataLayer
from equity_agent.data.fixtures import FixtureFilingSource
from equity_agent.llm import LlmError, cost_usd
from equity_agent.models import (
    AnalystOutput,
    LlmUsage,
    PeerPick,
    PeerPicks,
    PeerRationale,
    PeerRationales,
    FilingRef,
    PipelineEvent,
    ResearchReport,
    RiskItem,
    RiskSelection,
)
from equity_agent.pipeline import Pipeline, Services, run_report

PEERS = {
    "AAPL": ["MSFT", "GOOGL", "DELL", "HPQ"],
    "NVDA": ["AMD", "INTC", "AVGO", "QCOM"],
    "JPM": ["BAC", "C", "WFC", "GS"],
    "COST": ["WMT", "TGT", "BJ", "DG"],
    "TSLA": ["GM", "F", "TM", "RIVN"],
}
MODELS: dict[AgentName, str] = {
    "comps": "claude-opus-5-5",
    "risk": "claude-opus-5-5",
    "analyst": "claude-opus-5-5",
    "writer": "claude-sonnet-5-5",
}

Scripted = BaseModel | Exception | Callable[[dict[str, Any]], BaseModel]


def default_output(output_model: type[BaseModel], payload: dict[str, Any]) -> BaseModel:
    """A valid answer derived from the agent's input, chosen by the requested output type."""
    if output_model is PeerPicks:
        rejected = {r["ticker"] for r in payload.get("rejected_peers", [])}
        peers = [t for t in PEERS.get(payload["company"]["ticker"], ["MSFT", "GOOGL", "ORCL"]) if t not in rejected]
        return PeerPicks(peers=[PeerPick(ticker=t, name=f"{t} Corp") for t in peers])
    if output_model is PeerRationales:
        return PeerRationales(
            rationales=[PeerRationale(ticker=p["ticker"], rationale="Sells similar products.") for p in payload["peers"]]
        )
    if output_model is RiskSelection:
        headings = [h for h in payload["risk_headings"] if len(h.split()) > 5][:6]
        return RiskSelection(
            risks=[
                RiskItem(title=f"Risk {i + 1}", category="other", severity=2, explanation="Could hurt results.", source_heading=h)
                for i, h in enumerate(headings)
            ]
        )
    if output_model is AnalystOutput:
        preliminary = payload["scorecard"]["preliminary_signal"]
        return AnalystOutput(
            signal=preliminary,
            confidence=0.6,
            changed_from_preliminary=False,
            change_reason=None,
            valuation_summary="Valued in line with the scorecard.",
            thesis=["Strong margins.", "Solid balance sheet.", "Market leader."],
            counterpoints=["Premium valuation.", "Slower growth.", "Regulatory pressure."],
            signal_reasoning=f"The scorecard total is {payload['scorecard']['total']}; nothing justifies a change.",
        )
    raise ValueError(output_model)


def default_markdown(payload: dict[str, Any]) -> str:
    company = payload["company"]
    return (
        f"## Company overview\n\n{company['name']} trades at {company['price']}.\n\n"
        "## Financial commentary\n\nRevenue is shown by fiscal year in the table.\n\n"
        "## Comps commentary\n\nThe target is compared with its peer median.\n\n"
        "## Risk commentary\n\nThe main risks come from the annual filing.\n"
    )


class FakeClaude:
    def __init__(
        self,
        scripted: dict[AgentName, list[Scripted]] | None = None,
        *,
        delay: float = 0.0,
        markdown: str | Exception | None = None,
    ) -> None:
        self.scripted = {k: list(v) for k, v in (scripted or {}).items()}
        self.delay = delay
        self.markdown = markdown
        self.calls: list[tuple[AgentName, str]] = []
        self.spans: dict[AgentName, list[tuple[float, float]]] = {}

    def _usage(self, agent: AgentName, start: float, error: str | None = None) -> LlmUsage:
        model = MODELS[agent]
        return LlmUsage(
            agent=agent, model=model, input_tokens=1000, output_tokens=200, ms=int((time.perf_counter() - start) * 1000),
            cost_usd=cost_usd(model, 1000, 200), error=error,
        )  # fmt: skip

    async def parse(self, agent: AgentName, output_model: type[Any], system: str, user: str) -> tuple[Any, LlmUsage]:
        start = time.perf_counter()
        self.calls.append((agent, user))
        await asyncio.sleep(self.delay)
        self.spans.setdefault(agent, []).append((start, time.perf_counter()))
        payload = json.loads(user.split("\n\nYour previous answer")[0])
        queue = self.scripted.get(agent)
        item: Scripted = queue.pop(0) if queue else (lambda p: default_output(output_model, p))
        if isinstance(item, Exception):
            if isinstance(item, LlmError):
                item.usage = self._usage(agent, start, error=str(item))
            raise item
        output = item(payload) if callable(item) and not isinstance(item, BaseModel) else item
        return output, self._usage(agent, start)

    async def stream(
        self, agent: AgentName, system: str, user: str, on_usage: Callable[[LlmUsage], None]
    ) -> AsyncIterator[str]:
        start = time.perf_counter()
        self.calls.append((agent, user))
        if isinstance(self.markdown, Exception):
            on_usage(self._usage(agent, start, error=str(self.markdown)))
            raise self.markdown
        text = self.markdown if self.markdown is not None else default_markdown(json.loads(user))
        for index in range(0, len(text), 40):
            await asyncio.sleep(self.delay / 10)
            yield text[index : index + 40]
        self.spans.setdefault(agent, []).append((start, time.perf_counter()))
        on_usage(self._usage(agent, start))

    async def warm(self) -> None:
        return None

    async def close(self) -> None:
        return None

    def agents_called(self) -> list[AgentName]:
        return [agent for agent, _ in self.calls]


# ---- shared run helpers -------------------------------------------------------------------------------------------


def fake_services(llm: FakeClaude | None = None, data: DataLayer | None = None) -> Services:
    """Recorded data, an in-memory cache and a FakeClaude (default answers unless scripted)."""
    return Services(data=data or DataLayer.recorded(), llm=llm or FakeClaude())


def collect_events(services: Services, ticker: str = "AAPL", *, refresh: bool = False) -> list[PipelineEvent]:
    async def go() -> list[PipelineEvent]:
        return [event async for event in Pipeline(services).run(ticker, refresh=refresh)]

    return asyncio.run(go())


def make_report(llm: FakeClaude | None = None, ticker: str = "AAPL", data: DataLayer | None = None) -> ResearchReport:
    return asyncio.run(run_report(fake_services(llm, data), ticker))


def without_worker(services: Services) -> Services:
    """Make the API lifespan's parser start a no-op, so a test starts no process (parsing then runs inline)."""

    def start_parser() -> Future[bool]:
        done: Future[bool] = Future()
        done.set_result(True)
        return done

    setattr(services.data.sec, "start_parser", start_parser)
    return services


class SlowFilingSource(FixtureFilingSource):
    """Recorded filings whose risk text takes `seconds` of pure CPU work to read (top level, so it pickles)."""

    def __init__(self, seconds: float) -> None:
        super().__init__()
        self.seconds = seconds

    def risk_text(self, ref: FilingRef) -> str | None:
        end = time.perf_counter() + self.seconds
        while time.perf_counter() < end:
            sum(range(1000))
        return super().risk_text(ref)
