"""Async calls into capybucks, with the server guard around each one."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import TypeVar

import pandas as pd
from capybucks.async_api.download import download as async_download
from capybucks.async_api.download import infer_asset_type
from capybucks.async_api.ticker import AsyncTicker
from capybucks.core.models import Quote
from capybucks.core.registry import get_registry

from capybucks_mcp.errors import CallContextError
from capybucks_mcp.guard import get_guard
from capybucks_mcp.path_quote import install_quoted_path_templates

T = TypeVar("T")

install_quoted_path_templates()


def install_test_memory() -> None:
    """Replace the registry with MemoryProvider when the test env flag is set.

    The flag is for the stdio contract tests. It is not a market-data source.
    """
    if os.environ.get("CAPYBUCKS_MCP_TEST_MEMORY") != "1":
        return
    from capybucks.core.models import AssetType
    from capybucks.core.registry import reset_registry
    from capybucks.providers.memory import MemoryProvider

    reset_registry()
    get_registry().register(
        MemoryProvider(),
        default_for=((AssetType.EQUITY, "*"),),
    )


def unpack_frame(value: object) -> tuple[pd.DataFrame, str]:
    if (
        isinstance(value, tuple)
        and len(value) == 2
        and isinstance(value[0], pd.DataFrame)
        and isinstance(value[1], str)
    ):
        return value[0], value[1]
    raise TypeError("cache held an unexpected value")


def resolve_provider_name(
    symbol: str,
    provider: str | None,
    *,
    interval: str = "1d",
) -> str:
    source = get_registry().resolve(
        provider=provider,
        asset_type=infer_asset_type(symbol),
        interval=interval,
    )
    return source.name


async def _guarded(
    provider: str,
    capability: str,
    factory: Callable[[], Awaitable[T]],
) -> T:
    try:
        return await get_guard().run(provider, factory)
    except Exception as exc:
        raise CallContextError(exc, provider=provider, capability=capability) from exc


async def fetch_history(
    symbol: str,
    *,
    period: str,
    interval: str,
    start: datetime | None,
    end: datetime | None,
    auto_adjust: bool,
    provider: str | None,
    use_cache: bool,
) -> tuple[pd.DataFrame, str]:
    try:
        name = resolve_provider_name(symbol, provider, interval=interval)
    except Exception as exc:
        raise CallContextError(exc, provider=provider, capability="history") from exc

    async def _call() -> pd.DataFrame:
        return await async_download(
            symbol,
            period=period,
            interval=interval,
            start=start,
            end=end,
            auto_adjust=auto_adjust,
            provider=name,
            cache=use_cache,
        )

    frame = await _guarded(name, "history", _call)
    return frame, name


async def fetch_quote(symbol: str, provider: str | None) -> tuple[Quote, str]:
    try:
        name = resolve_provider_name(symbol, provider)
    except Exception as exc:
        raise CallContextError(exc, provider=provider, capability="quote") from exc
    ticker = AsyncTicker(symbol, provider=name)

    async def _call() -> Quote:
        return await ticker.quote()

    quote = await _guarded(name, "quote", _call)
    return quote, name


async def fetch_statement(
    symbol: str,
    provider: str | None,
    method: str,
) -> tuple[pd.DataFrame, str]:
    try:
        name = resolve_provider_name(symbol, provider)
    except Exception as exc:
        raise CallContextError(exc, provider=provider, capability="statements") from exc
    ticker = AsyncTicker(symbol, provider=name)

    async def _call() -> pd.DataFrame:
        fn = getattr(ticker, method)
        frame: pd.DataFrame = await fn()
        return frame

    try:
        frame = await _guarded(name, "statements", _call)
    except CallContextError:
        raise
    return frame, name


async def fetch_actions(symbol: str, provider: str | None) -> tuple[pd.DataFrame, str]:
    try:
        name = resolve_provider_name(symbol, provider)
    except Exception as exc:
        raise CallContextError(exc, provider=provider, capability="actions") from exc
    ticker = AsyncTicker(symbol, provider=name)

    async def _call() -> pd.DataFrame:
        return await ticker.actions()

    frame = await _guarded(name, "actions", _call)
    return frame, name


async def fetch_expirations(
    symbol: str, provider: str | None
) -> tuple[tuple[str, ...], str]:
    try:
        name = resolve_provider_name(symbol, provider)
    except Exception as exc:
        raise CallContextError(exc, provider=provider, capability="options") from exc
    ticker = AsyncTicker(symbol, provider=name)

    async def _call() -> tuple[str, ...]:
        return await ticker.options()

    dates = await _guarded(name, "options", _call)
    return dates, name


async def fetch_chain(
    symbol: str,
    provider: str | None,
    expiration: str | None,
) -> tuple[object, str]:
    try:
        name = resolve_provider_name(symbol, provider)
    except Exception as exc:
        raise CallContextError(exc, provider=provider, capability="options") from exc
    ticker = AsyncTicker(symbol, provider=name)

    async def _call() -> object:
        return await ticker.option_chain(expiration)

    chain = await _guarded(name, "options", _call)
    return chain, name


async def fetch_news(symbol: str, provider: str | None) -> tuple[pd.DataFrame, str]:
    try:
        name = resolve_provider_name(symbol, provider)
    except Exception as exc:
        raise CallContextError(exc, provider=provider, capability="news") from exc
    ticker = AsyncTicker(symbol, provider=name)

    async def _call() -> pd.DataFrame:
        return await ticker.news()

    frame = await _guarded(name, "news", _call)
    return frame, name
