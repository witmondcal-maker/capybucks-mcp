"""Argument checks that run before any provider call."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from capybucks_mcp.catalog import MAPPED_COINGECKO_SYMBOLS
from capybucks_mcp.config import (
    ABSOLUTE_MAX_LAST_N,
    ABSOLUTE_MAX_NEWS,
    ABSOLUTE_MAX_OPTION_ROWS,
    ABSOLUTE_MAX_PERIODS,
    ABSOLUTE_MAX_STATEMENT_ITEMS,
    ABSOLUTE_MAX_SYMBOLS,
    PERIODS,
    PROVIDER_INTERVALS,
    WINDOW_MAX,
    WINDOW_MIN,
    clamp_rows,
)

_SYMBOL = re.compile(r"^[A-Z0-9./^=-]{1,32}$")

INDICATORS = frozenset({"sma", "ema", "rsi", "macd", "bollinger", "atr", "vwap"})


def parse_symbols(symbols: str | list[str]) -> list[str]:
    """Accept one ticker, a comma/space separated string, or a list. Max 10."""
    if isinstance(symbols, str):
        raw_parts = symbols.replace(",", " ").split()
    else:
        raw_parts = []
        for item in symbols:
            raw_parts.extend(str(item).replace(",", " ").split())
    parsed: list[str] = []
    for part in raw_parts:
        token = part.strip().upper()
        if not token:
            continue
        if _SYMBOL.fullmatch(token) is None:
            raise ValueError(
                f"invalid symbol {token!r}; use letters, digits, and . - / ^ = only"
            )
        parsed.append(token)
    if not parsed:
        raise ValueError("at least one symbol is required")
    if len(parsed) > ABSOLUTE_MAX_SYMBOLS:
        raise ValueError(f"at most {ABSOLUTE_MAX_SYMBOLS} symbols per call")
    return parsed


def parse_symbol(symbol: str) -> str:
    return parse_symbols(symbol)[0]


def check_period(period: str) -> str:
    if period not in PERIODS:
        known = ", ".join(sorted(PERIODS))
        raise ValueError(f"unknown period {period!r}; expected one of {known}")
    return period


def check_interval(interval: str, provider: str | None) -> str:
    if provider is None:
        return interval
    allowed = PROVIDER_INTERVALS.get(provider)
    if allowed is not None and interval not in allowed:
        known = ", ".join(sorted(allowed))
        raise ValueError(
            f"provider {provider!r} does not support interval {interval!r}; "
            f"expected one of {known}"
        )
    return interval


def parse_datetime(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp. Naive values become UTC."""
    if value is None:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"invalid datetime {value!r}; use ISO-8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def parse_date(value: str) -> datetime:
    """Parse ``YYYY-MM-DD`` into a naive midnight datetime."""
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"invalid date {value!r}; use YYYY-MM-DD") from exc
    return parsed


def check_window(name: str, window: int) -> int:
    if window < WINDOW_MIN or window > WINDOW_MAX:
        raise ValueError(f"{name} must be between {WINDOW_MIN} and {WINDOW_MAX}")
    return window


def clamp_optional(
    requested: int | None,
    *,
    default: int,
    ceiling: int,
    name: str,
) -> int:
    if requested is None:
        return min(default, ceiling)
    if requested < 1:
        raise ValueError(f"{name} must be >= 1")
    return min(requested, ceiling)


def clamp_history_rows(requested: int | None) -> int:
    return clamp_rows(requested)


def clamp_periods(requested: int | None) -> int:
    return clamp_optional(
        requested, default=4, ceiling=ABSOLUTE_MAX_PERIODS, name="max_periods"
    )


def clamp_statement_items(count: int) -> int:
    return min(count, ABSOLUTE_MAX_STATEMENT_ITEMS)


def clamp_option_rows(requested: int | None) -> int:
    return clamp_optional(
        requested, default=50, ceiling=ABSOLUTE_MAX_OPTION_ROWS, name="max_rows"
    )


def clamp_news(requested: int | None) -> int:
    return clamp_optional(
        requested, default=10, ceiling=ABSOLUTE_MAX_NEWS, name="max_items"
    )


def clamp_last_n(requested: int | None) -> int:
    return clamp_optional(
        requested, default=30, ceiling=ABSOLUTE_MAX_LAST_N, name="last_n"
    )


def coingecko_unmapped(symbol: str) -> bool:
    return symbol.upper() not in MAPPED_COINGECKO_SYMBOLS
