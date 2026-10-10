"""Live USD instruments on KASE; actual KASE symbols and explicit US-listing reports.

RUN_LIVE_TESTS=1 uv run pytest -m live tests/test_kase_usd_live.py -q -s
The two US-listing reports use Claude/Tavily credits. Five native probes do not.
"""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from kase_cases import USD_NATIVE_CASES, USD_US_LISTING_CASES, KaseCase
from test_kase_live import Evidence, record_quote_case, record_report_case, settings  # noqa: F401 - shared pytest fixture

from equity_agent.config import BACKEND_ROOT, Settings

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def evidence() -> Iterator[Evidence]:
    stamp = datetime.now(timezone(timedelta(hours=5))).strftime("%d-%m-%Y-%H-%M-%S")
    directory = BACKEND_ROOT.parent / "docs" / f"kase-usd-{stamp}"
    directory.mkdir(parents=True, exist_ok=False)
    recorded = Evidence(directory)
    print(f"\nKASE USD evidence: {directory}", flush=True)
    try:
        yield recorded
    finally:
        recorded.finish()


@pytest.mark.parametrize("case", USD_NATIVE_CASES, ids=lambda case: case.id)
def test_native_kase_usd_quote(case: KaseCase, evidence: Evidence) -> None:
    record_quote_case(case, evidence)


@pytest.mark.parametrize("case", USD_US_LISTING_CASES, ids=lambda case: case.id)
def test_usd_kase_company_us_listing_report(case: KaseCase, settings: Settings, evidence: Evidence) -> None:
    record_report_case(case, settings, evidence)
