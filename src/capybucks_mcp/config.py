"""Process limits and environment normalization for the MCP server."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

ABSOLUTE_MAX_ROWS = 500
ABSOLUTE_MAX_PERIODS = 8
ABSOLUTE_MAX_STATEMENT_ITEMS = 60
ABSOLUTE_MAX_OPTION_ROWS = 100
ABSOLUTE_MAX_NEWS = 20
ABSOLUTE_MAX_LAST_N = 200
ABSOLUTE_MAX_SYMBOLS = 10
WINDOW_MIN = 2
WINDOW_MAX = 400
MAX_JSON_BYTES = 60 * 1024
DEFAULT_CONCURRENCY = 4
DEFAULT_CALL_TIMEOUT = 60.0
DEFAULT_COOLDOWN = 30.0

DEFAULT_TTLS: dict[str, float] = {
    "quote": 30.0,
    "news": 300.0,
    "options": 60.0,
    "statements": 6 * 3600.0,
    "actions": 6 * 3600.0,
}

PERIODS = frozenset(
    {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "max", "ytd"}
)

PROVIDER_INTERVALS: dict[str, frozenset[str]] = {
    "yahoo": frozenset(
        {
            "1m",
            "2m",
            "5m",
            "15m",
            "30m",
            "60m",
            "90m",
            "1h",
            "1d",
            "5d",
            "1wk",
            "1w",
            "1mo",
        }
    ),
    "twelvedata": frozenset({"1m", "5m", "15m", "30m", "1h", "1d", "1wk", "1w", "1mo"}),
    "coingecko": frozenset({"1d", "1h"}),
    "stooq": frozenset({"1d", "1wk", "1w", "1mo"}),
}

PROVIDERS = frozenset({"yahoo", "coingecko", "stooq", "twelvedata"})

ALLOWED_HOSTS = frozenset(
    {
        "query1.finance.yahoo.com",
        "api.coingecko.com",
        "api.twelvedata.com",
        "stooq.com",
    }
)

_PLACEHOLDER = re.compile(r"^\$\{[^}]+\}$")


@dataclass(frozen=True)
class McpConfig:
    """Limits read from the environment on each call."""

    max_rows_default: int
    max_rows_ceiling: int
    ttl_seconds: float | None
    concurrency: int
    call_timeout: float
    cooldown_seconds: float
    log_level: str


def normalize_process_env() -> None:
    """Drop empty or unresolved ``${VAR}`` placeholders from ``CAPYBUCKS_*``.

    Cursor may forward the literal placeholder when a plugin variable is left
    empty. Removing it lets capybucks fall through to ``~/.capybucks.toml``
    and surface ``MissingAPIKey`` instead of sending the placeholder as a key.
    """
    for key, value in list(os.environ.items()):
        if not key.startswith("CAPYBUCKS_"):
            continue
        stripped = value.strip()
        if stripped == "" or _PLACEHOLDER.fullmatch(stripped):
            del os.environ[key]


def _int_env(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def load_config() -> McpConfig:
    """Read optional MCP settings. Invalid values fall back to defaults."""
    requested = _int_env("CAPYBUCKS_MCP_MAX_ROWS")
    if requested is None:
        ceiling = ABSOLUTE_MAX_ROWS
        default_rows = min(100, ceiling)
    else:
        ceiling = max(1, min(ABSOLUTE_MAX_ROWS, requested))
        default_rows = ceiling
    ttl_raw = os.environ.get("CAPYBUCKS_MCP_TTL_SECONDS")
    ttl_seconds: float | None
    if ttl_raw is None or ttl_raw.strip() == "":
        ttl_seconds = None
    else:
        try:
            ttl_seconds = max(0.0, float(ttl_raw.strip()))
        except ValueError:
            ttl_seconds = None
    level = os.environ.get("CAPYBUCKS_MCP_LOG_LEVEL", "WARNING").strip() or "WARNING"
    return McpConfig(
        max_rows_default=default_rows,
        max_rows_ceiling=ceiling,
        ttl_seconds=ttl_seconds,
        concurrency=DEFAULT_CONCURRENCY,
        call_timeout=DEFAULT_CALL_TIMEOUT,
        cooldown_seconds=DEFAULT_COOLDOWN,
        log_level=level.upper(),
    )


def clamp_rows(requested: int | None, *, default: int | None = None) -> int:
    """Clamp a caller ``max_rows`` to the configured ceiling."""
    cfg = load_config()
    fallback = default if default is not None else cfg.max_rows_default
    if requested is None:
        return min(fallback, cfg.max_rows_ceiling)
    if requested < 1:
        raise ValueError("max_rows must be >= 1")
    return min(requested, cfg.max_rows_ceiling)


def ttl_for(kind: str) -> float:
    """Seconds to keep a non-history payload. ``0`` disables the memory cache."""
    cfg = load_config()
    if cfg.ttl_seconds == 0:
        return 0.0
    if cfg.ttl_seconds is not None:
        return cfg.ttl_seconds
    return DEFAULT_TTLS[kind]


def max_json_bytes() -> int:
    return MAX_JSON_BYTES
