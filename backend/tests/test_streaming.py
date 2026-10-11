"""Producer lifecycle regressions independent of providers and model latency."""

import asyncio

import pytest

from equity_agent.models import PipelineEvent
from equity_agent.streaming import SharedRun


@pytest.mark.parametrize("partial", [False, True])
def test_premature_eof_is_one_terminal_error(partial):
    async def scenario():
        async def source():
            if partial:
                yield PipelineEvent(event="stage", data={"stage": "risk", "status": "started"})
        run = SharedRun()
        await run.pump(source())
        events = [event async for event in run.follow()]
        assert len(events) == int(partial) + 1
        assert events[-1].event == "error" and events[-1].data["terminal"] is True
    asyncio.run(scenario())


def test_terminal_event_closes_producer_before_later_exception():
    async def scenario():
        closed = []
        async def source():
            try:
                yield PipelineEvent(event="error", data={"stage": "validate", "message": "bad", "terminal": True})
                raise AssertionError("producer advanced after terminal event")
            finally:
                closed.append(True)
        run = SharedRun()
        await run.pump(source())
        assert closed == [True] and len(run.events) == 1
    asyncio.run(scenario())


def test_late_subscriber_replays_partial_then_provider_exception():
    async def scenario():
        ready, release = asyncio.Event(), asyncio.Event()
        async def source():
            yield PipelineEvent(event="narrative", data={"delta": "partial"})
            ready.set()
            await release.wait()
            raise TimeoutError("fixture")
        run = SharedRun()
        task = asyncio.create_task(run.pump(source()))
        await ready.wait()
        follower = run.follow()
        assert (await anext(follower)).data["delta"] == "partial"
        release.set()
        await task
        remaining = [event async for event in follower]
        assert len(remaining) == 1 and remaining[0].data["terminal"] is True
    asyncio.run(scenario())
