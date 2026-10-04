"""Characterisation test: pins each fixture ticker's offline report and every agent input, byte for byte.

Refactors must leave these golden files unchanged. After an intended change, review the diff and rewrite them with
`UPDATE_GOLDEN=1 uv run pytest tests/test_characterisation.py`.
"""

import json
import os
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeClaude, collect_events, fake_services


GOLDEN_DIR = Path(__file__).parent / "golden"
TICKERS = ["AAPL", "NVDA", "JPM", "COST", "TSLA"]
VOLATILE_REPORT_FIELDS = {"generated_at", "timings_ms"}


def snapshot(ticker: str) -> dict[str, Any]:
    llm = FakeClaude()
    final = collect_events(fake_services(llm), ticker)[-1].data
    report = {k: v for k, v in final.items() if k not in VOLATILE_REPORT_FIELDS}
    for usage in report["llm_usage"]:
        usage.pop("ms", None)
    report["llm_usage"].sort(key=lambda u: (u["agent"], u["input_tokens"], u["output_tokens"]))
    # Concurrent branches call the agents in a nondeterministic order; sort for a stable comparison.
    calls = [{"agent": agent, "user": user} for agent, user in sorted(llm.calls)]
    return {"report": report, "agent_inputs": calls}


@pytest.mark.parametrize("ticker", TICKERS)
def test_report_and_agent_inputs_unchanged(ticker):
    path = GOLDEN_DIR / f"{ticker}.json"
    current = json.loads(json.dumps(snapshot(ticker), sort_keys=True, default=str))
    if os.environ.get("UPDATE_GOLDEN") == "1" or not path.exists():
        GOLDEN_DIR.mkdir(exist_ok=True)
        path.write_text(json.dumps(current, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")
        pytest.skip(f"golden file written: {path.name}")
    golden = json.loads(path.read_text(encoding="utf-8"))
    assert current["agent_inputs"] == golden["agent_inputs"], "an agent received different input"
    assert current["report"] == golden["report"], "the report changed"
