"""SEC EDGAR: fast latest-annual-filing lookup and compact risk-factor headings.

Parsing a 10-K's risk section is CPU-bound (JPM: ~17 s) and would hold the GIL in a thread, so it runs in a single
warm worker process started by `start_parser()`. Without a started pool (CLI, tests) it runs inline.
"""

from __future__ import annotations

import logging
import re
import sys
from concurrent.futures import Future, ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from datetime import date
from typing import Protocol

from edgar import Company, Filing, find, set_identity
from edgar.exceptions import CompanyNotFoundError
from edgar.paths import set_cache_directory

from equity_agent.cache import FILING_TTL, FOREVER, Cache
from equity_agent.config import BACKEND_ROOT
from equity_agent.models import Fetched, FilingRef, RiskHeadings, Unavailable

logger = logging.getLogger(__name__)

ANNUAL_FORMS = ["10-K", "20-F"]
EDGAR_CACHE_DIR = BACKEND_ROOT / ".cache" / "edgar"
MIN_HEADING_CHARS = 25
MAX_HEADING_CHARS = 260
TOKEN_BUDGET = 2000  # estimated as characters / 4
PARSE_TIMEOUT_S = 120
TRANSIENT = "temporarily unavailable: "  # reasons with this prefix are never cached

_FOOTER = re.compile(r"\|\s*(?:\d{4}\s+)?Form\s+(?:10-K|20-F)\s*\||^\s*(?:page\s+)?\d{1,3}\s*$", re.IGNORECASE)
_ITEM_TITLE = re.compile(r"^item\s+(?:1a|3\.d|3d)\b|^risk\s+factors\s*$", re.IGNORECASE)
_BULLET = re.compile(r"^[•●▪–—*\-]\s*")
_ENDS_SENTENCE = re.compile(r"[.;:?!)”\"]$")


def configure(identity: str) -> None:
    """Call once at start-up: SEC requires an identity on every request; filing downloads are cached on disk."""
    set_identity(identity)
    EDGAR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    set_cache_directory(EDGAR_CACHE_DIR)


def _logical_lines(text: str) -> list[str]:
    """Normalise whitespace, strip bullets and re-join hard-wrapped lines (common in 20-F filings)."""
    lines: list[str] = []
    for raw in text.splitlines():
        line = _BULLET.sub("", " ".join(raw.split()))
        if not line:
            continue
        if lines and line[0].islower() and not _ENDS_SENTENCE.search(lines[-1]):
            lines[-1] = f"{lines[-1]} {line}"
        else:
            lines.append(line)
    return lines


def extract_headings(text: str, token_budget: int = TOKEN_BUDGET) -> tuple[list[str], bool]:
    """Keep short standalone lines (the risk headings), in order, within a token budget.

    Body paragraphs are longer than MAX_HEADING_CHARS once wrapped lines are joined; footers, page numbers, item
    titles and lower-case fragments (list items inside body text) are dropped. Returns (headings, truncated).
    """
    headings: list[str] = []
    seen: set[str] = set()
    for line in _logical_lines(text):
        if not (MIN_HEADING_CHARS <= len(line) <= MAX_HEADING_CHARS) or not line[0].isupper():
            continue
        if _FOOTER.search(line) or _ITEM_TITLE.search(line) or line in seen:
            continue
        seen.add(line)
        headings.append(line)
    budget_chars = token_budget * 4
    used = 0
    for index, heading in enumerate(headings):
        used += len(heading) + 1
        if used > budget_chars:
            return headings[:index], True
    return headings, False


class FilingSource(Protocol):
    """Filing access. Implementations must pickle: `risk_text` runs in the parser worker process."""

    def latest_annual(self, ticker: str) -> FilingRef | None: ...

    def risk_text(self, ref: FilingRef) -> str | None: ...


class EdgarSource:
    def __init__(self, identity: str) -> None:
        self.identity = identity

    def latest_annual(self, ticker: str) -> FilingRef | None:
        try:
            company = Company(ticker)
        except CompanyNotFoundError:
            return None
        filing = company.get_filings(form=ANNUAL_FORMS, amendments=False, trigger_full_load=False).latest()
        return to_ref(ticker, filing) if isinstance(filing, Filing) else None

    def risk_text(self, ref: FilingRef) -> str | None:
        configure(self.identity)  # a spawned worker inherits neither the identity nor the cache directory
        filing = find(ref.accession_no)
        if not isinstance(filing, Filing):
            return None
        text = getattr(filing.obj(), "risk_factors", None)
        return str(text) if text else None


def to_ref(ticker: str, filing: Filing) -> FilingRef:
    url = getattr(filing, "filing_url", None) or getattr(filing, "homepage_url", "")
    return FilingRef(
        ticker=ticker,
        form=filing.form,
        filing_date=date.fromisoformat(str(filing.filing_date)[:10]),  # typed str, returned as date
        accession_no=filing.accession_no,
        url=url,
    )


def parse_risk_headings(source: FilingSource, ref: FilingRef) -> tuple[list[str], bool] | str:
    """Worker entry point (top level, so it pickles): (headings, truncated), or a reason when there are none."""
    text = source.risk_text(ref)
    if not text or not text.strip():
        return f"no risk-factor section found in the {ref.form}"
    headings, truncated = extract_headings(text)
    if not headings:
        return f"no risk headings could be extracted from the {ref.form}"
    return headings, truncated


def _warm_worker() -> bool:
    return "edgar" in sys.modules  # importing this module in the worker loaded edgartools


class SecData:
    def __init__(self, cache: Cache, source: FilingSource) -> None:
        self.cache = cache
        self.source = source
        self._pool: ProcessPoolExecutor | None = None

    # ---- worker lifecycle -------------------------------------------------------------------------------------

    def start_parser(self) -> Future[bool]:
        """Start the single parse worker and load edgartools in it. Returns the warm-up future."""
        if self._pool is None:
            self._pool = ProcessPoolExecutor(max_workers=1)
        return self._pool.submit(_warm_worker)

    def stop_parser(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
            self._pool = None

    @property
    def parser_running(self) -> bool:
        return self._pool is not None

    # ---- lookups ----------------------------------------------------------------------------------------------

    def latest_filing(self, ticker: str, *, refresh: bool = False) -> Fetched[FilingRef | Unavailable]:
        def load() -> FilingRef | Unavailable:
            ref = self.source.latest_annual(ticker)
            return ref or Unavailable(reason=f"no 10-K or 20-F found on SEC EDGAR for {ticker}")

        return self.cache.fetch(
            f"filing:{ticker}", FilingRef | Unavailable, FILING_TTL, load, refresh=refresh  # type: ignore[arg-type]
        )

    def risk_headings(self, ticker: str, *, refresh: bool = False) -> Fetched[RiskHeadings | Unavailable]:
        """Headings of the latest annual filing; cached by accession number forever, as a filing never changes."""
        ref = self.latest_filing(ticker, refresh=refresh)
        if isinstance(ref.value, Unavailable):
            return Fetched(ref.value, ref.hits)
        filing_ref = ref.value

        def load() -> RiskHeadings | Unavailable:
            outcome = self._parse(filing_ref)
            if isinstance(outcome, str):
                return Unavailable(reason=outcome)
            headings, truncated = outcome
            return RiskHeadings(filing=filing_ref, headings=headings, truncated=truncated)

        result = self.cache.fetch(
            f"risk:{filing_ref.accession_no}",
            RiskHeadings | Unavailable,  # type: ignore[arg-type]
            FOREVER,
            load,
            store=lambda value: not (isinstance(value, Unavailable) and value.reason.startswith(TRANSIENT)),
        )
        return Fetched(result.value, ref.hits + result.hits)

    def _parse(self, ref: FilingRef) -> tuple[list[str], bool] | str:
        if self._pool is None:
            return parse_risk_headings(self.source, ref)
        try:
            return self._pool.submit(parse_risk_headings, self.source, ref).result(timeout=PARSE_TIMEOUT_S)
        except BrokenProcessPool:
            logger.warning("Risk parser worker crashed; restarting it")
            self.stop_parser()
            self.start_parser()
            return f"{TRANSIENT}the filing parser stopped unexpectedly"
        except TimeoutError:
            return f"{TRANSIENT}the filing parser timed out after {PARSE_TIMEOUT_S} s"
