"""Shared research runs for the API: one pipeline run per ticker, replayed to every subscriber as Server-Sent Events.

A run is pumped by its own task, so a client that disconnects only stops its own stream; the run finishes and caches
its report. Clients that subscribe while a run is in progress get its events from the start, then live ones.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from equity_agent.data.market import try_normalize_ticker
from equity_agent.models import PipelineEvent
from equity_agent.pipeline import Pipeline, Services

logger = logging.getLogger(__name__)

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def sse(event: PipelineEvent) -> str:
    return f"event: {event.event}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"


def is_final(event: PipelineEvent) -> bool:
    return event.event == "report" or (event.event == "error" and bool(event.data.get("terminal")))


class SharedRun:
    """Every event of one pipeline run, kept for replay, with a wake-up for subscribers waiting on the next one."""

    def __init__(self) -> None:
        self.events: list[PipelineEvent] = []
        self.done = False
        self._changed = asyncio.Event()

    def _notify(self) -> None:
        self._changed.set()
        self._changed = asyncio.Event()

    async def pump(self, source: AsyncIterator[PipelineEvent]) -> None:
        try:
            async for event in source:
                self.events.append(event)
                self._notify()
                if is_final(event):
                    break
            if not self.events or not is_final(self.events[-1]):
                self._fail("research stream ended before completion")
        except Exception as error:  # noqa: BLE001 - subscribers must always get a final event
            logger.exception("research run failed")
            self._fail(f"unexpected error ({type(error).__name__})")
        finally:
            try:
                close = getattr(source, "aclose", None)
                if close is not None:
                    await close()
            except Exception as error:
                logger.exception("research producer cleanup failed")
                self._fail(f"unexpected error ({type(error).__name__})")
            finally:
                self.done = True
                self._notify()

    def _fail(self, message: str) -> None:
        if not self.events or not is_final(self.events[-1]):
            self.events.append(PipelineEvent(event="error", data={"stage": "pipeline", "message": message, "terminal": True}))

    async def follow(self) -> AsyncIterator[PipelineEvent]:
        """Every event from the start, then live ones, ending after the final event or when the run stops."""
        index = 0
        while True:
            while index < len(self.events):
                event = self.events[index]
                index += 1
                yield event
                if is_final(event):
                    return
            if self.done:
                return
            await self._changed.wait()


class RunRegistry:
    def __init__(self, services: Services) -> None:
        self.services = services
        self._runs: dict[str, SharedRun] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._closed = False
        self.started = 0  # pipeline runs started, for tests and logs

    def subscribe(self, raw_ticker: str, *, refresh: bool = False) -> AsyncIterator[PipelineEvent]:
        """Attach to the run in progress for this ticker, or start one. `refresh` only applies to a new run."""
        if self._closed:
            raise RuntimeError("research run registry is closed")
        key = try_normalize_ticker(raw_ticker) or raw_ticker  # invalid input still runs, to fail validation
        run = self._runs.get(key)
        if run is None:
            run = self._runs[key] = SharedRun()
            self.started += 1
            task = asyncio.create_task(run.pump(Pipeline(self.services).run(raw_ticker, refresh=refresh)))
            self._tasks.add(task)
            task.add_done_callback(lambda t: self._finished(key, run, t))
        return run.follow()

    def _finished(self, key: str, run: SharedRun, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        if self._runs.get(key) is run:
            del self._runs[key]

    async def wait_idle(self) -> None:
        """Wait for every run in progress to finish (tests)."""
        while self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            await asyncio.sleep(0)  # finished tasks leave the set in a done-callback; let it run

    async def close(self) -> None:
        """Stop accepting runs, cancel active work once, and drain it even when multiple callers close."""
        if not self._closed:
            self._closed = True
            for task in list(self._tasks):
                if not task.cancelling():
                    task.cancel()
        # Cancelling one close caller must not issue a second cancellation to a run draining provider threads.
        await asyncio.shield(asyncio.gather(*self._tasks, return_exceptions=True))


async def sse_stream(events: AsyncIterator[PipelineEvent]) -> AsyncIterator[str]:
    async for event in events:
        yield sse(event)
