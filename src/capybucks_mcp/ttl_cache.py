"""In-memory TTL for datasets the library does not cache."""

from __future__ import annotations

import time
from dataclasses import dataclass

from capybucks_mcp.config import ttl_for


@dataclass
class _Entry:
    value: object
    expires: float


class TTLCache:
    """Process-local cache. History stays on the library's parquet cache."""

    def __init__(self) -> None:
        self._data: dict[str, _Entry] = {}

    def get(self, key: str) -> object | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        if entry.expires <= time.monotonic():
            self._data.pop(key, None)
            return None
        return entry.value

    def put(self, key: str, value: object, ttl: float) -> None:
        if ttl <= 0:
            return
        self._data[key] = _Entry(value=value, expires=time.monotonic() + ttl)

    def put_kind(self, key: str, value: object, kind: str) -> None:
        self.put(key, value, ttl_for(kind))

    def clear(self) -> None:
        self._data.clear()


_cache: TTLCache | None = None


def get_ttl_cache() -> TTLCache:
    global _cache
    if _cache is None:
        _cache = TTLCache()
    return _cache


def reset_ttl_cache() -> None:
    global _cache
    _cache = TTLCache()
