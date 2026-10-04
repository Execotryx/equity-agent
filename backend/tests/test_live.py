"""Opt-in tests against real services: `RUN_LIVE_TESTS=1 uv run pytest -m live`. They may spend credits."""

import time

import pytest

from equity_agent.config import load_settings
from equity_agent.data import sec

pytestmark = pytest.mark.live


def test_jpm_annual_filing_lookup_is_fast():
    settings = load_settings()
    sec.configure(settings.edgar_identity)
    start = time.perf_counter()
    ref = sec.EdgarSource(settings.edgar_identity).latest_annual("JPM")
    elapsed = time.perf_counter() - start
    assert ref is not None and ref.form == "10-K"
    assert elapsed < 5, f"lookup took {elapsed:.1f} s"


def test_gateway_parse_on_opus_and_stream_on_sonnet():
    import asyncio

    from equity_agent.llm import Gateway
    from equity_agent.models import LlmUsage, PeerPicks

    gateway = Gateway(load_settings())
    usages: list[LlmUsage] = []

    async def go() -> tuple[PeerPicks, str]:
        try:
            picks, usage = await gateway.parse(
                "comps", PeerPicks, "Return 3 US-listed peers of the given company.", "Costco (COST)"
            )
            usages.append(usage)
            text = "".join([t async for t in gateway.stream("writer", "Answer in one sentence.", "What does Costco sell?", usages.append)])
            return picks, text
        finally:
            await gateway.close()

    picks, text = asyncio.run(go())
    assert 1 <= len(picks.peers) <= 5 and text.strip()
    assert [u.model for u in usages] == ["claude-opus-5-5", "claude-sonnet-5-5"]
    assert all(u.output_tokens > 0 and u.cost_usd > 0 and u.error is None for u in usages)
