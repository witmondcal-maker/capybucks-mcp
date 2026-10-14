"""``get_financials`` and ``get_dividends_and_splits``."""

from __future__ import annotations

from typing import Literal

from capybucks.exceptions import ProviderError

from capybucks_mcp.envelope import DELAY_UNKNOWN, YAHOO_WARNING, success
from capybucks_mcp.errors import CallContextError, failure_envelope
from capybucks_mcp.runtime import fetch_actions, fetch_statement, unpack_frame
from capybucks_mcp.serialize import (
    action_rows,
    statement_payload,
    thin_provenance,
    truncation,
)
from capybucks_mcp.ttl_cache import get_ttl_cache
from capybucks_mcp.validate import (
    clamp_history_rows,
    clamp_periods,
    parse_datetime,
    parse_symbol,
)

_METHODS = {
    ("income", "annual"): "financials",
    ("income", "quarterly"): "quarterly_financials",
    ("balance", "annual"): "balance_sheet",
    ("balance", "quarterly"): "quarterly_balance_sheet",
    ("cashflow", "annual"): "cashflow",
    ("cashflow", "quarterly"): "quarterly_cashflow",
}


def _provider_warnings(name: str) -> list[str]:
    warnings = [DELAY_UNKNOWN]
    if name == "yahoo":
        warnings.append(YAHOO_WARNING)
    return warnings


async def get_financials(
    symbol: str,
    statement: Literal["income", "balance", "cashflow"] = "income",
    frequency: Literal["annual", "quarterly"] = "annual",
    provider: Literal["yahoo", "coingecko", "stooq", "twelvedata"] | None = None,
    items: list[str] | None = None,
    max_periods: int | None = None,
) -> dict[str, object]:
    try:
        parsed = parse_symbol(symbol)
        periods_limit = clamp_periods(max_periods)
        method = _METHODS[(statement, frequency)]
        cache_key = f"statement|{provider or ''}|{parsed}|{method}"
        cached = get_ttl_cache().get(cache_key)
        if cached is None:
            frame, name = await fetch_statement(parsed, provider, method)
            get_ttl_cache().put_kind(cache_key, (frame, name), "statements")
        else:
            frame, name = unpack_frame(cached)
        if frame.empty:
            raise CallContextError(
                ProviderError("statement returned no line items"),
                provider=name,
                capability="statements",
            )
        periods, rows, filter_miss = statement_payload(
            frame, items=items, max_periods=periods_limit
        )
        warnings = _provider_warnings(name)
        if filter_miss:
            warnings.append("No statement items matched the filter.")
        elif not rows:
            raise CallContextError(
                ProviderError("statement returned no line items"),
                provider=name,
                capability="statements",
            )
        return success(
            tool="get_financials",
            data={
                "symbol": parsed,
                "statement": statement,
                "frequency": frequency,
                "periods": periods,
                "items": rows,
            },
            provenance=thin_provenance(name),
            truncation=truncation(len(frame.columns), len(periods)),
            warnings=warnings,
        )
    except Exception as exc:
        return failure_envelope("get_financials", exc)


async def get_dividends_and_splits(
    symbol: str,
    kind: Literal["both", "dividends", "splits"] = "both",
    since: str | None = None,
    max_rows: int | None = None,
    provider: Literal["yahoo", "coingecko", "stooq", "twelvedata"] | None = None,
) -> dict[str, object]:
    try:
        parsed = parse_symbol(symbol)
        since_dt = parse_datetime(since)
        limit = clamp_history_rows(max_rows)
        cache_key = f"actions|{provider or ''}|{parsed}"
        cached = get_ttl_cache().get(cache_key)
        if cached is None:
            frame, name = await fetch_actions(parsed, provider)
            get_ttl_cache().put_kind(cache_key, (frame, name), "actions")
        else:
            frame, name = unpack_frame(cached)
        dividends = action_rows(frame, column="Dividends", since=since_dt)
        splits = action_rows(frame, column="Stock Splits", since=since_dt)
        if kind == "dividends":
            splits = []
        elif kind == "splits":
            dividends = []
        total = len(dividends) + len(splits)
        dividends = dividends[-limit:]
        splits = splits[-limit:]
        returned = len(dividends) + len(splits)
        return success(
            tool="get_dividends_and_splits",
            data={"symbol": parsed, "dividends": dividends, "splits": splits},
            provenance=thin_provenance(name),
            truncation=truncation(total, returned),
            warnings=_provider_warnings(name),
        )
    except Exception as exc:
        return failure_envelope("get_dividends_and_splits", exc)
