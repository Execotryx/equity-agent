"""Filing sources for the process-pool tests. They live in an importable module so spawned workers can unpickle them."""

from __future__ import annotations

import os
import time
from pathlib import Path

from equity_agent.data.fixtures import FixtureFilingSource
from equity_agent.models import FilingRef


class PidSource(FixtureFilingSource):
    """Returns the worker's PID as the only heading."""

    def risk_text(self, ref: FilingRef) -> str | None:
        return f"Risk heading from process number {os.getpid()} here"


class CrashOnceSource(FixtureFilingSource):
    """Kills the worker the first time; the marker file records that it already crashed."""

    def __init__(self, marker: Path) -> None:
        super().__init__()
        self.marker = marker

    def risk_text(self, ref: FilingRef) -> str | None:
        if not self.marker.exists():
            self.marker.write_text("crashed", encoding="utf-8")
            os._exit(1)
        return super().risk_text(ref)


class BusySource(FixtureFilingSource):
    """CPU-bound for about 2 seconds, like a large 10-K parse."""

    def risk_text(self, ref: FilingRef) -> str | None:
        end = time.perf_counter() + 2.0
        total = 0
        while time.perf_counter() < end:
            total += sum(range(1000))
        return super().risk_text(ref)
