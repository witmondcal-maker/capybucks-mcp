"""Global concurrency limit, per-provider cooldown, and per-call timeout."""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from capybucks.exceptions import RateLimitError

from capybucks_mcp.config import load_config

T = TypeVar("T")


class CooldownActive(Exception):
    """The provider is in the server cooldown window after a rate limit."""

    def __init__(self, provider: str, retry_after_seconds: int) -> None:
        self.provider = provider
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"{provider} is in cooldown for {retry_after_seconds}s after a rate limit"
        )


class Guard:
    """Serialize bursts without replacing the library's own per-provider spacing."""

    def __init__(
        self,
        *,
        concurrency: int | None = None,
        timeout: float | None = None,
        cooldown: float | None = None,
    ) -> None:
        cfg = load_config()
        self.concurrency = concurrency if concurrency is not None else cfg.concurrency
        self.timeout = timeout if timeout is not None else cfg.call_timeout
        self.cooldown = cooldown if cooldown is not None else cfg.cooldown_seconds
        self._sem = asyncio.Semaphore(self.concurrency)
        self._until: dict[str, float] = {}

    def retry_after(self, provider: str) -> float | None:
        until = self._until.get(provider)
        if until is None:
            return None
        remaining = until - time.monotonic()
        if remaining <= 0:
            self._until.pop(provider, None)
            return None
        return remaining

    def trip(self, provider: str) -> None:
        self._until[provider] = time.monotonic() + self.cooldown

    def reset(self) -> None:
        self._until.clear()

    async def run(self, provider: str, factory: Callable[[], Awaitable[T]]) -> T:
        remaining = self.retry_after(provider)
        if remaining is not None:
            raise CooldownActive(provider, max(1, math.ceil(remaining)))
        async with self._sem:
            remaining = self.retry_after(provider)
            if remaining is not None:
                raise CooldownActive(provider, max(1, math.ceil(remaining)))
            try:
                return await asyncio.wait_for(factory(), self.timeout)
            except RateLimitError:
                self.trip(provider)
                raise


_guard: Guard | None = None


def get_guard() -> Guard:
    global _guard
    if _guard is None:
        _guard = Guard()
    return _guard


def reset_guard() -> None:
    global _guard
    _guard = Guard()
