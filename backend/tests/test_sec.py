import asyncio
import os
import time
from datetime import date

import pytest
from sec_helpers import BusySource, CrashOnceSource, PidSource

from equity_agent.cache import Cache
from equity_agent.data.fixtures import FixtureFilingSource
from equity_agent.data.sec import TOKEN_BUDGET, SecData, extract_headings
from equity_agent.models import FilingRef, RiskHeadings, Unavailable


@pytest.fixture
def sec() -> SecData:
    return SecData(Cache(None), FixtureFilingSource())


def test_latest_filing_for_domestic_filer(sec):
    ref = sec.latest_filing("AAPL").value
    assert isinstance(ref, FilingRef)
    assert ref.form == "10-K" and ref.accession_no and ref.url.startswith("https://www.sec.gov/")


def test_aapl_headings(sec):
    result = sec.risk_headings("AAPL").value
    assert isinstance(result, RiskHeadings)
    assert 20 <= len(result.headings) <= 80
    assert not any("Form 10-K |" in h for h in result.headings)
    assert not any(h.lower().startswith("item 1a") for h in result.headings)


@pytest.mark.parametrize("ticker", ["NVDA", "JPM", "COST", "TSLA"])
def test_headings_within_budget(sec, ticker):
    result = sec.risk_headings(ticker).value
    assert isinstance(result, RiskHeadings) and result.headings
    assert sum(len(h) + 1 for h in result.headings) <= TOKEN_BUDGET * 4


def test_extraction_drops_footers_titles_and_body():
    text = "\n".join(
        [
            "Item 1A.    Risk Factors",
            "Competition could adversely impact our market share and results.",
            "Apple Inc. | 2025 Form 10-K | 7",
            "12",
            "x" * 400,  # body paragraph
            "Supply disruptions could affect our ability to ship products.",
        ]
    )
    headings, truncated = extract_headings(text)
    assert headings == [
        "Competition could adversely impact our market share and results.",
        "Supply disruptions could affect our ability to ship products.",
    ]
    assert truncated is False


def test_extraction_joins_wrapped_lines_and_strips_bullets():
    text = "•Long manufacturing lead times and uncertain supply may\nharm our results.\n•suppliers failing to deliver"
    headings, _ = extract_headings(text)
    assert headings == ["Long manufacturing lead times and uncertain supply may harm our results."]


def test_oversized_section_truncated_at_heading_boundary():
    text = "\n".join(f"Risk heading number {i} could adversely affect our business." for i in range(500))
    headings, truncated = extract_headings(text)
    assert truncated is True
    assert sum(len(h) + 1 for h in headings) <= TOKEN_BUDGET * 4
    assert headings[-1].endswith("business.")


def test_no_filing_is_unavailable(sec):
    result = sec.risk_headings("ZZZZQX").value
    assert isinstance(result, Unavailable) and "no 10-K or 20-F" in result.reason


class EmptySection(FixtureFilingSource):
    def risk_text(self, ref):
        return "   "


def test_empty_risk_section_is_unavailable():
    result = SecData(Cache(None), EmptySection()).risk_headings("AAPL").value
    assert isinstance(result, Unavailable) and "no risk-factor section" in result.reason


class CountingSource(FixtureFilingSource):
    def __init__(self) -> None:
        super().__init__()
        self.parses = 0

    def risk_text(self, ref):
        self.parses += 1
        return super().risk_text(ref)


def test_headings_cached_by_accession_forever():
    source = CountingSource()
    sec = SecData(Cache(None), source)
    sec.risk_headings("AAPL")
    hits = sec.risk_headings("AAPL", refresh=True).hits
    assert source.parses == 1
    ref = sec.latest_filing("AAPL").value
    assert isinstance(ref, FilingRef) and f"risk:{ref.accession_no}" in hits


def test_unavailable_reason_is_readable():
    ref = FilingRef(ticker="X", form="20-F", filing_date=date(2026, 1, 1), accession_no="1", url="u")
    assert "20-F" in SecData(Cache(None), EmptySection())._parse(ref)  # type: ignore[operator]


# ---- worker process --------------------------------------------------------------------------------------------


def test_parse_runs_in_warm_worker_process():
    sec = SecData(Cache(None), PidSource())
    try:
        assert sec.start_parser().result(timeout=120) is True
        result = sec.risk_headings("AAPL").value
        assert isinstance(result, RiskHeadings)
        worker_pid = int(result.headings[0].split("number ")[1].split()[0])
        assert worker_pid != os.getpid()
    finally:
        sec.stop_parser()


def test_crashed_worker_yields_unavailable_then_recovers(tmp_path):
    sec = SecData(Cache(None), CrashOnceSource(tmp_path / "crashed"))
    try:
        sec.start_parser().result(timeout=120)
        first = sec.risk_headings("AAPL").value
        assert isinstance(first, Unavailable) and "stopped unexpectedly" in first.reason
        second = sec.risk_headings("AAPL").value  # the transient failure was not cached
        assert isinstance(second, RiskHeadings)
    finally:
        sec.stop_parser()


def test_event_loop_keeps_running_during_cpu_bound_parse():
    sec = SecData(Cache(None), BusySource())
    sec.start_parser().result(timeout=120)

    async def scenario() -> float:
        gaps: list[float] = []
        parse = asyncio.create_task(asyncio.to_thread(sec.risk_headings, "AAPL"))
        last = time.perf_counter()
        while not parse.done():
            await asyncio.sleep(0.02)
            now = time.perf_counter()
            gaps.append(now - last)
            last = now
        await parse
        return max(gaps)

    try:
        assert asyncio.run(scenario()) < 0.1
    finally:
        sec.stop_parser()
