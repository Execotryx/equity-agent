"""Recorded provider data for offline tests and the offline demo mode.

Layout per ticker in `backend/tests/fixtures/<T>/`: `info.json`, `income.json`, `closes.json`, `filing.json`,
`risk_text.txt`, `search_competitors.json`, `search_news.json`. Written by `scripts/record_fixtures.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from equity_agent.config import BACKEND_ROOT
from equity_agent.data.search import Topic
from equity_agent.models import FilingRef

FIXTURES_DIR = BACKEND_ROOT / "tests" / "fixtures"


class FixtureMissing(LookupError):
    pass


def _read(directory: Path, ticker: str, name: str) -> Any:
    path = directory / ticker / name
    if not path.exists():
        raise FixtureMissing(f"no recorded {name} for {ticker}")
    text = path.read_text(encoding="utf-8")
    return json.loads(text) if name.endswith(".json") else text


class FixtureMarketSource:
    def __init__(self, directory: Path = FIXTURES_DIR) -> None:
        self.directory = directory

    def info(self, ticker: str) -> dict[str, Any]:
        try:
            return _read(self.directory, ticker, "info.json")
        except FixtureMissing:
            return {"trailingPegRatio": None}  # what Yahoo returns for unknown symbols

    def income(self, ticker: str) -> dict[str, dict[str, float | None]]:
        return _read(self.directory, ticker, "income.json")

    def closes(self, ticker: str) -> list[tuple[str, float]]:
        return [(d, c) for d, c in _read(self.directory, ticker, "closes.json")]


class FixtureFilingSource:
    def __init__(self, directory: Path = FIXTURES_DIR) -> None:
        self.directory = directory

    def latest_annual(self, ticker: str) -> FilingRef | None:
        try:
            return FilingRef.model_validate(_read(self.directory, ticker, "filing.json"))
        except FixtureMissing:
            return None

    def risk_text(self, ref: FilingRef) -> str | None:
        try:
            return _read(self.directory, ref.ticker, "risk_text.txt")
        except FixtureMissing:
            return None


class FixtureSearchSource:
    """Serves recorded searches by matching the query to a ticker's recorded company name."""

    def __init__(self, directory: Path = FIXTURES_DIR) -> None:
        self.directory = directory
        self.companies: dict[str, str] = {}  # lower-case company name -> ticker folder, read once
        for info_path in sorted(directory.glob("*/info.json")):
            name = json.loads(info_path.read_text(encoding="utf-8")).get("longName", "")
            if name:
                self.companies[name.lower()] = info_path.parent.name

    def search(self, query: str, *, topic: Topic, days: int | None) -> dict[str, Any]:
        name = "search_news.json" if topic == "news" else "search_competitors.json"
        for company, ticker in self.companies.items():
            if query.lower().startswith(company) and (self.directory / ticker / name).exists():
                return _read(self.directory, ticker, name)
        return {"results": []}
