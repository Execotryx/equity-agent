import pytest
from tavily.errors import InvalidAPIKeyError, MissingAPIKeyError, UsageLimitExceededError

from equity_agent.cache import Cache
from equity_agent.data.fixtures import FixtureSearchSource
from equity_agent.data.search import MAX_RESULTS, SNIPPET_CHARS, SearchData, TavilySource
from equity_agent.models import SearchResults, Unavailable

SECRET = "tvly-secret-value-123"


@pytest.fixture
def search() -> SearchData:
    return SearchData(Cache(None), FixtureSearchSource())


def test_competitor_search_bounded(search):
    outcome = search.competitors("Costco Wholesale Corporation", "Discount Stores").value
    assert isinstance(outcome, SearchResults) and 1 <= len(outcome.items) <= MAX_RESULTS
    for item in outcome.items:
        assert item.url.startswith("http") and item.domain and "www." not in item.domain
        assert 0 < len(item.snippet) <= SNIPPET_CHARS


def test_news_search(search):
    outcome = search.news("NVIDIA Corporation").value
    assert isinstance(outcome, SearchResults) and 1 <= len(outcome.items) <= MAX_RESULTS
    assert all(item.title and item.url for item in outcome.items)


class CountingSource(FixtureSearchSource):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def search(self, query, *, topic, days):
        self.calls += 1
        return super().search(query, topic=topic, days=days)


def test_repeated_query_served_from_cache():
    source = CountingSource()
    search = SearchData(Cache(None), source)
    search.news("Apple Inc.")
    second = search.news("Apple Inc.")
    assert second.hit and source.calls == 1


class FailingSource:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    def search(self, query, *, topic, days):
        self.calls += 1
        raise self.error


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (MissingAPIKeyError(), "not configured"),
        (InvalidAPIKeyError(f"bad key {SECRET}"), "not configured"),
        (UsageLimitExceededError(f"limit for {SECRET}"), "quota exhausted"),
        (ConnectionError(f"failed with {SECRET}"), "service error"),
    ],
)
def test_failures_become_empty_results(error, reason, caplog):
    source = FailingSource(error)
    search = SearchData(Cache(None), source)
    outcome = search.competitors("Apple Inc.", "Consumer Electronics").value
    assert isinstance(outcome, Unavailable) and outcome.reason == reason
    assert SECRET not in outcome.reason and SECRET not in caplog.text
    search.competitors("Apple Inc.", "Consumer Electronics")
    assert source.calls == 2  # failures are not cached


def test_missing_key_never_calls_service():
    with pytest.raises(MissingAPIKeyError):
        TavilySource("").search("x", topic="general", days=None)


def test_refresh_bypasses_cached_results():
    source = CountingSource()
    search = SearchData(Cache(None), source)
    search.news("Apple Inc.")
    fresh = search.news("Apple Inc.", refresh=True)
    assert not fresh.hit and source.calls == 2
    assert search.news("Apple Inc.").hit  # the refreshed result was stored
