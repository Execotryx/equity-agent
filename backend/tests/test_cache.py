from equity_agent.cache import Cache
from equity_agent.models import YearValue


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def counting_loader(value: int):
    calls = []

    def load() -> YearValue:
        calls.append(1)
        return YearValue(year=2025, value=value)

    return load, calls


def test_fresh_entry_is_a_hit():
    cache = Cache(None)
    load, calls = counting_loader(1)
    first = cache.fetch("k", YearValue, 60, load)
    second = cache.fetch("k", YearValue, 60, load)
    assert (first.hit, second.hit) == (False, True)
    assert second.value == YearValue(year=2025, value=1)
    assert len(calls) == 1


def test_expired_entry_is_refetched():
    clock = Clock()
    cache = Cache(None, clock=clock)
    load, calls = counting_loader(1)
    cache.fetch("k", YearValue, 60, load)
    clock.now += 61
    assert cache.fetch("k", YearValue, 60, load).hit is False
    assert len(calls) == 2


def test_no_expiry_entry_survives_a_month():
    clock = Clock()
    cache = Cache(None, clock=clock)
    load, calls = counting_loader(1)
    cache.fetch("risk:acc", YearValue, None, load)
    clock.now += 31 * 24 * 3600
    assert cache.fetch("risk:acc", YearValue, None, load).hit is True
    assert len(calls) == 1


def test_entries_persist_across_connections(tmp_path):
    path = tmp_path / "cache.db"
    first = Cache(path)
    first.fetch("k", YearValue, 60, counting_loader(7)[0])
    first.close()
    load, calls = counting_loader(8)
    result = Cache(path).fetch("k", YearValue, 60, load)
    assert result.hit and result.value.value == 7 and not calls


def test_refresh_bypasses_and_overwrites():
    cache = Cache(None)
    cache.fetch("k", YearValue, 60, counting_loader(1)[0])
    refreshed = cache.fetch("k", YearValue, 60, counting_loader(2)[0], refresh=True)
    assert refreshed.hit is False and refreshed.value.value == 2
    assert cache.fetch("k", YearValue, 60, counting_loader(3)[0]).value.value == 2


def test_corrupt_entry_is_discarded_and_refetched():
    cache = Cache(None)
    cache.set_raw("k", "{not json", 60)
    load, calls = counting_loader(5)
    result = cache.fetch("k", YearValue, 60, load)
    assert result.hit is False and result.value.value == 5 and len(calls) == 1


def test_store_veto_skips_caching():
    cache = Cache(None)
    load, calls = counting_loader(1)
    cache.fetch("k", YearValue, 60, load, store=lambda v: False)
    cache.fetch("k", YearValue, 60, load, store=lambda v: False)
    assert len(calls) == 2
