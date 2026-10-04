"""Research pipeline (IMPLEMENTATION_PLAN.md §4.2): one fast, fault-tolerant run per ticker as an event stream.

validate -> [financials | comps | risk | news] concurrently -> scorecard -> [analyst | writer] concurrently -> report.
Blocking data calls run in threads (`asyncio.to_thread`); 10-K parsing runs in the data layer's worker process.
Only a validation failure ends a run early; any other failing branch degrades its section.

Every consumer (CLI, evaluation, tests) gets a report through `run_report`; the API streams `Pipeline.run` events.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, TypeVar

from pydantic import BaseModel

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
    fallback_peers,
    parse_sections,
    ungrounded_numbers,
)
from equity_agent.agents.base import ClaudeAgent, StageFailed
from equity_agent.cache import FOREVER, PEERS_TTL, REPORT_TTL, Cache
from equity_agent.config import DEFAULT_EFFORT, DEFAULT_MODELS, AgentConfig, AgentName, ScoringConfig, Settings
from equity_agent.data import DataError, DataLayer, normalize_ticker
from equity_agent.llm import Gateway, LlmClient
from equity_agent.models import (
    AnalystView,
    CompsTable,
    Fetched,
    FilingRef,
    FinancialProfile,
    History,
    LlmUsage,
    NewsItem,
    PeerChoice,
    PeerOrigin,
    PipelineEvent,
    Quote,
    ReportNarrative,
    ResearchReport,
    RiskReport,
    RiskSelection,
    SearchResult,
    Snapshot,
    StageError,
    Unavailable,
)
from equity_agent.scoring import DEFAULT_SCORING, assemble_comps, build_scorecard

logger = logging.getLogger(__name__)

T = TypeVar("T")
Out = TypeVar("Out", bound=BaseModel)


def _default_models() -> dict[AgentName, AgentConfig]:
    return {agent: AgentConfig(model=model, effort=DEFAULT_EFFORT) for agent, model in DEFAULT_MODELS.items()}


@dataclass
class Services:
    data: DataLayer
    llm: LlmClient
    scoring: ScoringConfig = DEFAULT_SCORING
    comps_agent: CompsAgent = field(default_factory=CompsAgent)
    comps_explain_agent: CompsExplainAgent = field(default_factory=CompsExplainAgent)
    risk_agent: RiskAgent = field(default_factory=RiskAgent)
    analyst_agent: AnalystAgent = field(default_factory=AnalystAgent)
    writer_agent: WriterAgent = field(default_factory=WriterAgent)
    models: Mapping[AgentName, AgentConfig] = field(default_factory=_default_models)  # names the agent caches


def live_services(settings: Settings) -> Services:
    """Real data providers, the persistent cache and the Claude gateway; the demo recording when offline."""
    if settings.offline:
        from equity_agent.demo import offline_services  # demo builds on this module

        return offline_services(settings)
    return Services(data=DataLayer.live(settings), llm=Gateway(settings), models=settings.agents)


class RunFailed(Exception):
    """A run that ended with a terminal error, such as an unknown ticker. `reason` is the user-facing text."""

    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(f"{stage}: {reason}")
        self.stage = stage
        self.reason = reason


class _Run:
    """State of one pipeline run: the event queue, timings, usage records, cache hits and warnings."""

    def __init__(self, services: Services, refresh: bool) -> None:
        self.s = services
        self.refresh = refresh
        self.queue: asyncio.Queue[PipelineEvent | None] = asyncio.Queue()
        self.start = time.perf_counter()
        self.timings: dict[str, int] = {}
        self.usage: list[LlmUsage] = []
        self.record_usage: Callable[[LlmUsage], None] = self.usage.append  # every model call reports here
        self.hits: list[str] = []
        self.warnings: list[str] = []
        self.comps_explain: asyncio.Task[CompsTable] | None = None

    # ---- plumbing --------------------------------------------------------------------------------------------

    def emit(self, event: str, **data: Any) -> None:
        self.queue.put_nowait(PipelineEvent(event=event, data=data))  # type: ignore[arg-type]

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.start) * 1000)

    def partial(self, key: str, value: BaseModel | list[Any]) -> None:
        if isinstance(value, BaseModel):
            payload: Any = value.model_dump(mode="json")
        else:
            payload = [v.model_dump(mode="json") if isinstance(v, BaseModel) else v for v in value]
        self.emit("partial", key=key, value=payload)

    def fail(self, stage: str, message: str, *, terminal: bool = False) -> StageError:
        self.emit("error", stage=stage, message=message, terminal=terminal)
        return StageError(stage=stage, message=message)

    def use(self, fetched: Fetched[T]) -> T:
        """Unwrap a data-layer result, recording the cache keys it was served from."""
        self.hits.extend(fetched.hits)
        return fetched.value

    async def fetch(self, call: Callable[..., Fetched[T]], *args: Any, **kwargs: Any) -> Fetched[T]:
        """Run a blocking data-layer call in a thread, recording its cache hits. The caller reads `.value`, and
        `.hit` for its own stage's cached flag (branches run concurrently, so the shared hit list can't tell)."""
        fetched = await asyncio.to_thread(call, *args, **kwargs)
        self.use(fetched)
        return fetched

    async def agent(self, agent: ClaudeAgent[Any, Out], data: Any) -> Out:
        """Run one agent; its usage is recorded call by call, whether it succeeds or raises StageFailed."""
        return (await agent.run(self.s.llm, data, self.record_usage)).output

    def model(self, agent: AgentName) -> str:
        return self.s.models[agent].model

    async def stage(self, name: str, work: Callable[[], Awaitable[tuple[T, bool]]]) -> T:
        """Run one stage with started/done events; `work` returns (result, served_from_cache)."""
        self.emit("stage", stage=name, status="started")
        started = time.perf_counter()
        done: dict[str, Any] = {}
        try:
            result, cached = await work()
            done = {"status": "done", "cached": cached}
            return result
        finally:  # a failure propagates; either way the stage's duration is recorded and reported
            self.timings[name] = int((time.perf_counter() - started) * 1000)
            self.emit("stage", stage=name, ms=self.timings[name], **(done or {"status": "failed"}))

    async def section(
        self, name: str, work: Callable[[], Awaitable[tuple[T, bool]]], unavailable: str, suffix: str = ""
    ) -> T | StageError:
        """A stage whose failure degrades its report section instead of the run.

        An agent failure keeps its own message; anything else is logged and reported as "<unavailable> (<type>)".
        """
        try:
            return await self.stage(name, work)
        except StageFailed as error:
            message = str(error)
        except Exception as error:  # noqa: BLE001 - degrade the section, keep the run
            logger.exception("%s failed", name)
            message = f"{unavailable} ({type(error).__name__})"
        return self.fail(name, message + suffix)

    # ---- branches --------------------------------------------------------------------------------------------

    async def financials(self, quote: Quote) -> FinancialProfile:
        async def work() -> tuple[FinancialProfile, bool]:
            try:
                fetched = await self.fetch(self.s.data.market.history, quote.snapshot.ticker, refresh=self.refresh)
            except DataError as error:  # the profile still has the snapshot and multiples
                self.warnings.append(f"financial history unavailable ({error.detail or error.reason})")
                return build_profile(quote, History()), False
            return build_profile(quote, fetched.value), fetched.hit

        profile = await self.stage("financials", work)
        self.partial("financials", profile)
        return profile

    async def comps(self, quote: Quote) -> tuple[CompsTable | StageError, list[SearchResult]]:
        """Build and emit the comps table; fresh peers get their rationales from a background explain call."""
        snap = quote.snapshot
        choice_key = f"peers:{snap.ticker}:{self.model('comps')}"
        search_results: list[SearchResult] = []
        fresh = False

        async def work() -> tuple[CompsTable, bool]:
            nonlocal search_results, fresh
            choice = self.use(self.s.data.cache.lookup(choice_key, PeerChoice, refresh=self.refresh))
            if choice is not None:
                return await self.comps_table(quote, choice.tickers, **choice.table_kwargs()), True
            found = (await self.fetch(self.s.data.search.competitors, snap.name, snap.industry, refresh=self.refresh)).value
            if isinstance(found, Unavailable):
                self.warnings.append(f"competitor search unavailable: {found.reason}")
            else:
                search_results = found.items
            fresh = True
            return await self.pick_peers(quote, search_results), False

        table = await self.section("comps", work, unavailable="comps unavailable")
        if isinstance(table, StageError):
            return table, search_results
        if table.insufficient:
            return self.fail("comps", f"only {len(table.peers)} eligible peers found"), search_results
        self.timings["comps_ready"] = self.elapsed_ms()
        self.partial("comps", table)
        if fresh:  # rationales don't feed the scorecard, Analyst or Writer, so nothing downstream waits for them
            self.comps_explain = asyncio.create_task(self.explain_peers(snap, table, search_results, choice_key))
        return table, search_results

    async def comps_table(self, quote: Quote, tickers: Sequence[str], **kwargs: Any) -> CompsTable:
        batch = (await self.fetch(self.s.data.market.peers, list(tickers), refresh=self.refresh)).value
        return assemble_comps(quote, tickers, batch, config=self.s.scoring, **kwargs)

    async def pick_peers(self, quote: Quote, search: list[SearchResult]) -> CompsTable:
        """The Comps Agent's pick call, one re-ask listing rejected tickers, then the static sector list."""
        snap = quote.snapshot
        sources = [r.url for r in search]
        agent_input = CompsInput(snapshot=snap, search=search)
        candidates: list[str] = []
        table: CompsTable | None = None
        for attempt in range(2):
            try:
                picks = await self.agent(self.s.comps_agent, agent_input)
            except StageFailed as error:
                self.warnings.append(f"comps agent failed: {error}")
                break
            candidates = [normalize_ticker(p.ticker) for p in picks.peers]  # validated by the agent
            table = await self.comps_table(quote, candidates, sources=sources)
            if not table.insufficient or attempt == 1:
                break
            agent_input = CompsInput(snapshot=snap, search=search, rejected=table.exclusions)

        if table is not None and not table.insufficient:
            return table
        included = [r.ticker for r in table.peers] if table else []
        extra = fallback_peers(snap.sector, {snap.ticker, *included})
        origin: dict[str, PeerOrigin] = {**{t: "agent" for t in candidates}, **{t: "fallback" for t in extra}}
        self.warnings.append("static sector peers were used to complete the comps table")
        return await self.comps_table(quote, included + extra, origin=origin, sources=sources)

    async def explain_peers(
        self, target: Snapshot, table: CompsTable, search: list[SearchResult], choice_key: str
    ) -> CompsTable:
        """The Comps Agent's explain call, then a second comps partial; caches the peer choice once explained."""

        async def work() -> tuple[CompsTable, bool]:
            output = await self.agent(self.s.comps_explain_agent, ExplainInput(target, table.peers, search))
            rationales = {normalize_ticker(r.ticker): r.rationale for r in output.rationales}  # validated
            return table.model_copy(update={"peer_rationales": rationales}), False

        explained = await self.section("comps_explain", work, unavailable="explain call failed")
        if isinstance(explained, StageError):  # not cached, so the next run retries
            self.warnings.append(f"peer rationales unavailable: {explained.message}")
            return table
        self.s.data.cache.set(choice_key, PeerChoice.from_table(explained), PeerChoice, PEERS_TTL)
        self.partial("comps", explained)
        return explained

    async def risk(self, quote: Quote) -> RiskReport | StageError:
        snap = quote.snapshot

        async def work() -> tuple[RiskReport | Unavailable, bool]:
            fetched = await self.fetch(self.s.data.sec.risk_headings, snap.ticker)
            headings = fetched.value
            if isinstance(headings, Unavailable):
                return headings, fetched.hit
            agent_input = RiskInput(snap.name, snap.ticker, headings.filing.form, headings.headings)
            selected = await self.s.data.cache.afetch(
                f"riskreport:{headings.filing.accession_no}:{self.model('risk')}",
                RiskSelection,
                FOREVER,
                lambda: self.agent(self.s.risk_agent, agent_input),
            )
            report = RiskReport(
                filing=headings.filing,
                headings=headings.headings,
                headings_truncated=headings.truncated,
                risks=self.use(selected).risks,
            )
            return report, selected.hit  # cached when no model call was needed

        result = await self.section("risk", work, unavailable="SEC filing unavailable")
        if isinstance(result, Unavailable):
            return self.fail("risk", result.reason)
        if isinstance(result, RiskReport):
            self.partial("risks", result)
        return result

    async def news(self, quote: Quote) -> tuple[list[NewsItem], str | None]:
        async def work() -> tuple[list[NewsItem] | Unavailable, bool]:
            fetched = await self.fetch(self.s.data.search.news, quote.snapshot.name, refresh=self.refresh)
            found = fetched.value
            return (found if isinstance(found, Unavailable) else found.items), fetched.hit

        result = await self.section("news", work, unavailable="service error")
        if isinstance(result, StageError):
            items, reason = [], result.message
        elif isinstance(result, Unavailable):
            items, reason = [], result.reason
            self.fail("news", f"news unavailable: {reason}")
        else:
            items, reason = result, None
        self.partial("news", items)
        return items, reason

    async def analyst(self, agent_input: AnalystInput) -> AnalystView | StageError:
        async def work() -> tuple[AnalystView, bool]:
            output = await self.agent(self.s.analyst_agent, agent_input)
            preliminary = agent_input.scorecard.preliminary_signal
            return AnalystView(**output.model_dump(), preliminary_signal=preliminary, reviewed=True), False

        view = await self.section(
            "analyst", work, unavailable="analyst unavailable", suffix="; the preliminary signal was not reviewed"
        )
        if isinstance(view, AnalystView):
            self.timings["signal_ready"] = self.elapsed_ms()
            self.partial("analyst", view)
        return view

    async def writer(self, writer_input: WriterInput) -> tuple[ReportNarrative | StageError, str]:
        agent = self.s.writer_agent
        chunks: list[str] = []

        async def work() -> tuple[str, bool]:
            async for text in agent.stream(self.s.llm, writer_input, self.record_usage):
                chunks.append(text)
                self.emit("narrative", delta=text)
            return "".join(chunks), False

        markdown = await self.section("writer", work, unavailable="narrative unavailable")
        if isinstance(markdown, StageError):
            return markdown, "".join(chunks)
        narrative, problems = parse_sections(markdown)
        self.warnings.extend(f"narrative: {p}" for p in problems)
        unmatched = ungrounded_numbers(markdown, agent.build_user(writer_input))
        if unmatched:
            self.warnings.append("narrative numbers not found in the input: " + ", ".join(unmatched))
        return narrative, markdown


class Pipeline:
    def __init__(self, services: Services) -> None:
        self.services = services

    async def run(self, raw_ticker: str, *, refresh: bool = False) -> AsyncIterator[PipelineEvent]:
        """Yield progress events; the last one is `report`, or an `error` with `terminal: true`."""
        state = _Run(self.services, refresh)
        task = asyncio.create_task(self._execute(state, raw_ticker))
        try:
            while True:
                event = await state.queue.get()
                if event is None:
                    break
                yield event
        finally:
            if not task.done():
                await task  # let the run finish (and cache its report) even if the consumer stops early
            elif task.exception() is not None:
                raise task.exception()  # type: ignore[misc]

    async def _execute(self, state: _Run, raw_ticker: str) -> None:
        try:
            await self._steps(state, raw_ticker)
        except Exception as error:  # noqa: BLE001 - never leave a consumer waiting
            logger.exception("pipeline failed")
            state.fail("pipeline", f"unexpected error ({type(error).__name__})", terminal=True)
        finally:
            state.queue.put_nowait(None)

    async def _steps(self, state: _Run, raw_ticker: str) -> None:
        s = self.services
        # ---- 0. validate ------------------------------------------------------------------------------------
        state.emit("stage", stage="validate", status="started")
        try:
            ticker = normalize_ticker(raw_ticker)
            fetched = await asyncio.to_thread(s.data.market.quote, ticker, refresh=state.refresh)
        except DataError as error:
            state.fail("validate", error.reason, terminal=True)
            return
        quote = state.use(fetched)
        state.timings["validate"] = state.elapsed_ms()
        state.emit("stage", stage="validate", status="done", ms=state.timings["validate"], cached=fetched.hit)

        if not state.refresh:
            cached = cached_report(s.data.cache, ticker)
            if cached is not None:
                state.emit("report", **cached.model_dump(mode="json"), from_cache=True)
                return
        state.partial("snapshot", quote.snapshot)

        # ---- 1. concurrent branches -------------------------------------------------------------------------
        profile, (comps, search), risks, (news, news_error) = await asyncio.gather(
            state.financials(quote), state.comps(quote), state.risk(quote), state.news(quote)
        )

        # ---- 2. scorecard -----------------------------------------------------------------------------------
        table = comps if isinstance(comps, CompsTable) else None
        scorecard = build_scorecard(quote, table, profile.price_history, s.scoring)
        state.timings["scorecard"] = 0
        state.partial("scorecard", scorecard)

        # ---- 3. analyst and writer together, then the peers' rationales -------------------------------------
        risk_items = risks.risks if isinstance(risks, RiskReport) else None
        analyst, (narrative, markdown) = await asyncio.gather(
            state.analyst(AnalystInput(profile, table, risk_items, scorecard, news)),
            state.writer(WriterInput(profile, table, risk_items, news)),
        )
        if state.comps_explain is not None:
            comps = await state.comps_explain  # never raises: a failed explain keeps the table without rationales

        # ---- 4. report --------------------------------------------------------------------------------------
        state.timings["total"] = state.elapsed_ms()
        report = ResearchReport(
            generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
            ticker=ticker,
            financials=profile,
            comps=comps,
            competitor_search=search,
            risks=risks,
            news=news,
            news_error=news_error,
            scorecard=scorecard,
            analyst=analyst,
            signal=analyst.signal if isinstance(analyst, AnalystView) else scorecard.preliminary_signal,
            signal_reviewed=isinstance(analyst, AnalystView),
            narrative=narrative,
            narrative_markdown=markdown,
            timings_ms=state.timings,
            llm_usage=state.usage,
            cache_hits=list(dict.fromkeys(state.hits)),
            quality_warnings=state.warnings,
        )
        s.data.cache.set(_report_key(ticker), report, ResearchReport, REPORT_TTL)
        state.emit("report", **report.model_dump(mode="json"), from_cache=False)


@dataclass
class WarmResult:
    ticker: str
    status: Literal["ok", "degraded", "failed"]  # failed: the ticker didn't validate, so nothing was cached
    ms: int
    problems: list[str] = field(default_factory=list)  # degraded sections and quality warnings


async def warm_ticker(services: Services, raw_ticker: str) -> WarmResult:
    """Run the pipeline up to the scorecard so the data, peer choice and risk selection are cached.

    The Analyst and Writer don't run, so warming costs only the Comps and Risk calls. A cached report is dropped, so the
    next report streams live, with only the Analyst and Writer left to run.
    """
    state = _Run(services, refresh=False)
    try:
        ticker = normalize_ticker(raw_ticker)
        quote = state.use(await asyncio.to_thread(services.data.market.quote, ticker))
    except DataError as error:
        return WarmResult(raw_ticker, "failed", state.elapsed_ms(), [error.reason])
    services.data.cache.delete(_report_key(ticker))
    await asyncio.gather(state.financials(quote), state.comps(quote), state.risk(quote), state.news(quote))
    if state.comps_explain is not None:
        await state.comps_explain  # the peer choice is cached only once explained
    problems = [f"{e.data['stage']}: {e.data['message']}" for e in _drain(state.queue) if e.event == "error"]
    return WarmResult(ticker, "degraded" if problems else "ok", state.elapsed_ms(), problems + state.warnings)


def _drain(queue: asyncio.Queue[PipelineEvent | None]) -> list[PipelineEvent]:
    events: list[PipelineEvent] = []
    while not queue.empty():
        event = queue.get_nowait()
        if event is not None:
            events.append(event)
    return events


def _report_key(ticker: str) -> str:
    return f"report:{ticker}"


def cached_report(cache: Cache, ticker: str) -> ResearchReport | None:
    """The unexpired report for a normalised ticker, or None."""
    return cache.get(_report_key(ticker), ResearchReport)


def clear_agent_caches(cache: Cache, ticker: str) -> None:
    """Forget the cached report, peer choice and risk selection for a ticker, keeping market and filing data."""
    cache.delete(_report_key(ticker))
    cache.delete_prefix(f"peers:{ticker}:")
    filing = cache.get(f"filing:{ticker}", FilingRef | Unavailable)
    if isinstance(filing, FilingRef):
        cache.delete_prefix(f"riskreport:{filing.accession_no}:")


def report_from_event(event: PipelineEvent) -> ResearchReport:
    data = {k: v for k, v in event.data.items() if k != "from_cache"}
    return ResearchReport.model_validate(data)


async def run_report(
    services: Services,
    ticker: str,
    *,
    refresh: bool = False,
    on_event: Callable[[PipelineEvent], None] | None = None,
) -> ResearchReport:
    """The one way to get a report: runs the pipeline, forwards events, raises RunFailed on a terminal error."""
    report: ResearchReport | None = None
    async for event in Pipeline(services).run(ticker, refresh=refresh):
        if on_event is not None:
            on_event(event)
        if event.event == "error" and event.data.get("terminal"):
            raise RunFailed(event.data["stage"], event.data["message"])
        if event.event == "report":
            report = report_from_event(event)
    if report is None:
        raise RunFailed("pipeline", "the run ended without a report")
    return report
