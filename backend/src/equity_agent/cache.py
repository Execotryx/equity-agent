"""Persistent SQLite cache with a time-to-live per entry (IMPLEMENTATION_PLAN.md §4.6).

Values are stored as JSON and decoded with a pydantic TypeAdapter, so any model or union of models can be cached.
One connection is shared across threads behind a lock; every operation is a single short statement.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

from pydantic import TypeAdapter

from equity_agent.config import BACKEND_ROOT
from equity_agent.models import Fetched

logger = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = BACKEND_ROOT / ".cache" / "research.db"

# Lifetimes in seconds; None means the entry never expires.
QUOTE_TTL = 15 * 60
HISTORY_TTL = 24 * 3600
FILING_TTL = 24 * 3600
SEARCH_TTL = 7 * 24 * 3600
PEERS_TTL = 7 * 24 * 3600
REPORT_TTL = 3600
FOREVER: float | None = None

M = TypeVar("M")

_adapters: dict[Any, TypeAdapter[Any]] = {}


def _adapter(tp: Any) -> TypeAdapter[Any]:
    if tp not in _adapters:
        _adapters[tp] = TypeAdapter(tp)
    return _adapters[tp]


class Cache:
    def __init__(self, path: Path | None = DEFAULT_CACHE_PATH, clock: Callable[[], float] = time.time) -> None:
        """`path=None` keeps the cache in memory (tests)."""
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(":memory:" if path is None else str(path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL, expires_at REAL)"
        )
        self._lock = threading.Lock()
        self._clock = clock

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def get_raw(self, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute("SELECT value, expires_at FROM cache WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        value, expires_at = row
        if expires_at is not None and expires_at <= self._clock():
            return None
        return value

    def set_raw(self, key: str, value: str, ttl: float | None) -> None:
        expires_at = None if ttl is None else self._clock() + ttl
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)", (key, value, expires_at)
            )
            self._conn.commit()

    def delete(self, key: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            self._conn.commit()

    def delete_prefix(self, prefix: str) -> int:
        """Remove every entry whose key starts with `prefix`; returns the number removed."""
        with self._lock:
            cursor = self._conn.execute("DELETE FROM cache WHERE substr(key, 1, ?) = ?", (len(prefix), prefix))
            self._conn.commit()
        return cursor.rowcount

    def get(self, key: str, tp: Any) -> Any | None:
        """Decoded value or None when absent, expired or corrupt (a corrupt entry is removed)."""
        raw = self.get_raw(key)
        if raw is None:
            return None
        try:
            return _adapter(tp).validate_json(raw)
        except ValueError:
            logger.warning("Discarding unreadable cache entry %s", key)
            self.delete(key)
            return None

    def set(self, key: str, value: Any, tp: Any, ttl: float | None) -> None:
        self.set_raw(key, _adapter(tp).dump_json(value).decode(), ttl)

    def lookup(self, key: str, tp: Any, *, refresh: bool = False) -> Fetched[Any | None]:
        """The cached value (None when absent or when `refresh` asks to skip the cache), reporting a hit."""
        cached = None if refresh else self.get(key, tp)
        return Fetched(cached, [key] if cached is not None else [])

    async def afetch(
        self,
        key: str,
        tp: type[M] | Any,
        ttl: float | None,
        loader: Callable[[], Awaitable[M]],
        *,
        refresh: bool = False,
        store: Callable[[M], bool] | None = None,
    ) -> Fetched[M]:
        """`fetch` for an async loader (an agent call)."""
        found = self.lookup(key, tp, refresh=refresh)
        if found.value is not None:
            return found  # type: ignore[return-value]
        value = await loader()
        if store is None or store(value):
            self.set(key, value, tp, ttl)
        return Fetched(value)

    def fetch(
        self,
        key: str,
        tp: type[M] | Any,
        ttl: float | None,
        loader: Callable[[], M],
        *,
        refresh: bool = False,
        store: Callable[[M], bool] | None = None,
    ) -> Fetched[M]:
        """Return the cached value, or call `loader`, store its result and return it.

        `refresh` skips the read but still overwrites the entry. `store` can veto caching a result
        (for example a transient failure).
        """
        found = self.lookup(key, tp, refresh=refresh)
        if found.value is not None:
            return found  # type: ignore[return-value]
        value = loader()
        if store is None or store(value):
            self.set(key, value, tp, ttl)
        return Fetched(value)
