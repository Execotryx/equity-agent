"""Export real pipeline event sequences for the frontend tests: `uv run python scripts/export_ui_fixtures.py`.

Runs the pipeline on recorded data with FakeClaude (no keys, no network) and writes one JSON list of events per case
to frontend/src/test/fixtures/, in the shape the stream sends: {"event": ..., "data": ...}.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "tests"))

from fakes import FakeClaude, fake_services  # noqa: E402

from equity_agent.llm import LlmError  # noqa: E402
from equity_agent.models import PipelineEvent  # noqa: E402
from equity_agent.pipeline import Pipeline, Services  # noqa: E402

OUT = BACKEND.parent / "frontend" / "src" / "test" / "fixtures"


async def events(services: Services, ticker: str) -> list[PipelineEvent]:
    return [event async for event in Pipeline(services).run(ticker)]


def save(name: str, recorded: list[PipelineEvent]) -> None:
    path = OUT / f"{name}.json"
    path.write_text(json.dumps([e.model_dump(mode="json") for e in recorded], indent=1) + "\n", encoding="utf-8")
    print(f"{path.relative_to(BACKEND.parent)}: {len(recorded)} events, last {recorded[-1].event}")


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    aapl = fake_services()
    save("aapl", await events(aapl, "AAPL"))
    save("aapl-cached", await events(aapl, "AAPL"))  # same services: the report is now cached
    save("jpm", await events(fake_services(), "JPM"))
    save("unknown-ticker", await events(fake_services(), "ZZZZQX"))
    risk_fails = FakeClaude({"risk": [LlmError("refusal", "model declined the request")]})
    save("aapl-risk-failed", await events(fake_services(risk_fails), "AAPL"))


if __name__ == "__main__":
    asyncio.run(main())
