"""Tavily web search: one competitor search and one 30-day news search per report, both basic depth (1 credit).

Failures never raise to the caller: they become an empty result with a reason that never contains the key.
"""

from __future__ import annotations

import logging
from typing import Any, Literal, Protocol
from urllib.parse import urlparse

from tavily import TavilyClient
from tavily.errors import ForbiddenError, InvalidAPIKeyError, MissingAPIKeyError, UsageLimitExceededError

from equity_agent.cache import SEARCH_TTL, Cache
from equity_agent.formatting import truncate_words
from equity_agent.models import Fetched, NewsItem, SearchResult, SearchResults, Unavailable

logger = logging.getLogger(__name__)

MAX_RESULTS = 5
SNIPPET_CHARS = 600
NEWS_DAYS = 30
SEARCH_TIMEOUT_S = 15


Topic = Literal["general", "news"]


class SearchSource(Protocol):
    def search(self, query: str, *, topic: Topic, days: int | None) -> dict[str, Any]: ...


class TavilySource:
    def __init__(self, api_key: str) -> None:
        self._client = TavilyClient(api_key=api_key) if api_key else None

    def search(self, query: str, *, topic: Topic, days: int | None) -> dict[str, Any]:
        if self._client is None:
            raise MissingAPIKeyError()
        kwargs: dict[str, Any] = {"days": days} if days else {}
        return self._client.search(
            query, search_depth="basic", topic=topic, max_results=MAX_RESULTS, timeout=SEARCH_TIMEOUT_S, **kwargs
        )


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host.removeprefix("www.")


def _snippet(text: str) -> str:
    return truncate_words(" ".join((text or "").split()), SNIPPET_CHARS)


def failure_reason(error: Exception) -> str:
    if isinstance(error, MissingAPIKeyError | InvalidAPIKeyError | ForbiddenError):
        return "not configured"
    if isinstance(error, UsageLimitExceededError):
        return "quota exhausted"
    return "service error"


class SearchData:
    def __init__(self, cache: Cache, source: SearchSource) -> None:
        self.cache = cache
        self.source = source

    def _run(
        self, key: str, tp: Any, query: str, topic: Topic, days: int | None, build: Any, refresh: bool
    ) -> Fetched[Any]:
        def load() -> Any:
            try:
                raw = self.source.search(query, topic=topic, days=days)
            except Exception as error:  # noqa: BLE001 - search is optional; degrade instead of failing the report
                reason = failure_reason(error)
                logger.warning("Search failed (%s): %s", reason, type(error).__name__)
                return Unavailable(reason=reason)
            return tp(items=[build(r) for r in raw.get("results", [])[:MAX_RESULTS] if r.get("url")])

        # Failed searches are not cached, so a fixed key or restored quota takes effect immediately.
        return self.cache.fetch(
            key,
            tp | Unavailable,
            SEARCH_TTL,
            load,
            refresh=refresh,
            store=lambda outcome: not isinstance(outcome, Unavailable),
        )

    def competitors(
        self, name: str, industry: str | None, *, refresh: bool = False
    ) -> Fetched[SearchResults[SearchResult] | Unavailable]:
        query = f"{name} main competitors {industry or ''}".strip()
        return self._run(
            f"tavily:competitors:{query.lower()}",
            SearchResults[SearchResult],
            query,
            "general",
            None,
            lambda r: SearchResult(
                title=r.get("title") or "", url=r["url"], domain=_domain(r["url"]), snippet=_snippet(r.get("content", ""))
            ),
            refresh,
        )

    def news(self, name: str, *, refresh: bool = False) -> Fetched[SearchResults[NewsItem] | Unavailable]:
        query = f"{name} stock news"
        return self._run(
            f"tavily:news:{query.lower()}",
            SearchResults[NewsItem],
            query,
            "news",
            NEWS_DAYS,
            lambda r: NewsItem(
                title=r.get("title") or "", url=r["url"], domain=_domain(r["url"]), published=r.get("published_date")
            ),
            refresh,
        )
