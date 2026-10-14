"""``get_option_expirations`` and ``get_option_chain``."""

from __future__ import annotations

from typing import Literal, cast

from capybucks.core.frames import OptionChainFrames

from capybucks_mcp.envelope import DELAY_UNKNOWN, YAHOO_WARNING, success
from capybucks_mcp.errors import failure_envelope
from capybucks_mcp.runtime import fetch_chain, fetch_expirations, fetch_history
from capybucks_mcp.serialize import option_rows, thin_provenance
from capybucks_mcp.ttl_cache import get_ttl_cache
from capybucks_mcp.validate import clamp_option_rows, parse_symbol

_NEAR_MONEY_BAND = 0.15


def _warnings(name: str) -> list[str]:
    warnings = [DELAY_UNKNOWN]
    if name == "yahoo":
        warnings.append(YAHOO_WARNING)
    return warnings


async def get_option_expirations(
    symbol: str,
    provider: Literal["yahoo", "coingecko", "stooq", "twelvedata"] | None = None,
) -> dict[str, object]:
    try:
        parsed = parse_symbol(symbol)
        cache_key = f"expirations|{provider or ''}|{parsed}"
        cached = get_ttl_cache().get(cache_key)
        if isinstance(cached, tuple):
            dates, name = cached
        else:
            dates, name = await fetch_expirations(parsed, provider)
            get_ttl_cache().put_kind(cache_key, (dates, name), "options")
        if not isinstance(dates, tuple):
            raise TypeError("option expiration cache held an unexpected value")
        if not isinstance(name, str):
            raise TypeError("option expiration cache held an unexpected provider")
        return success(
            tool="get_option_expirations",
            data={"symbol": parsed, "expirations": list(dates)},
            provenance=thin_provenance(name),
            warnings=_warnings(name),
        )
    except Exception as exc:
        return failure_envelope("get_option_expirations", exc)


async def get_option_chain(
    symbol: str,
    expiration: str | None = None,
    side: Literal["both", "calls", "puts"] = "both",
    near_money: bool = True,
    strike_min: float | None = None,
    strike_max: float | None = None,
    max_rows: int | None = None,
    provider: Literal["yahoo", "coingecko", "stooq", "twelvedata"] | None = None,
) -> dict[str, object]:
    warnings: list[str] = []
    try:
        parsed = parse_symbol(symbol)
        limit = clamp_option_rows(max_rows)
        cache_key = f"chain|{provider or ''}|{parsed}|{expiration or ''}"
        cached = get_ttl_cache().get(cache_key)
        if isinstance(cached, tuple):
            chain, name = cached
        else:
            chain, name = await fetch_chain(parsed, provider, expiration)
            get_ttl_cache().put_kind(cache_key, (chain, name), "options")
        if not isinstance(name, str):
            raise TypeError("option chain cache held an unexpected provider")
        frames = cast(OptionChainFrames, chain)
        warnings.extend(_warnings(name))
        calls = option_rows(frames.calls)
        puts = option_rows(frames.puts)
        spot: float | None = None
        if near_money:
            spot, spot_warning = await _spot(parsed, name)
            if spot_warning:
                warnings.append(spot_warning)
            elif spot is not None:
                warnings.append(
                    "near_money used the last daily close from the same provider "
                    "to keep strikes within 15% of that close."
                )
        spot_for_filter = spot if near_money else None
        calls, calls_note = _filter_strikes(
            calls, strike_min=strike_min, strike_max=strike_max, spot=spot_for_filter
        )
        puts, puts_note = _filter_strikes(
            puts, strike_min=strike_min, strike_max=strike_max, spot=spot_for_filter
        )
        if calls_note:
            warnings.append(calls_note)
        elif puts_note:
            warnings.append(puts_note)
        if side == "calls":
            puts = []
        elif side == "puts":
            calls = []
        calls_total = len(calls)
        puts_total = len(puts)
        calls, calls_flag = _cap(calls, limit, spot_for_filter)
        puts, puts_flag = _cap(puts, limit, spot_for_filter)
        chosen = expiration or _expiration_of(frames)
        return success(
            tool="get_option_chain",
            data={
                "symbol": parsed,
                "expiration": chosen,
                "calls": calls,
                "puts": puts,
            },
            provenance=thin_provenance(name),
            truncation={
                "rows_total": calls_total + puts_total,
                "rows_returned": len(calls) + len(puts),
                "truncated": calls_flag or puts_flag,
                "kept": "closest_to_spot"
                if spot_for_filter is not None
                else "lowest_strikes",
            },
            warnings=warnings,
        )
    except Exception as exc:
        return failure_envelope("get_option_chain", exc, extra_warnings=warnings)


def _expiration_of(frames: OptionChainFrames) -> str | None:
    for frame in (frames.calls, frames.puts):
        if "expiration" in frame.columns and not frame.empty:
            value = frame["expiration"].iloc[0]
            if isinstance(value, str):
                return value
    return None


async def _spot(symbol: str, provider: str) -> tuple[float | None, str | None]:
    try:
        frame, _name = await fetch_history(
            symbol,
            period="5d",
            interval="1d",
            start=None,
            end=None,
            auto_adjust=True,
            provider=provider,
            use_cache=True,
        )
    except Exception:
        return None, (
            "near_money could not load the last daily close; strikes were not centered."
        )
    if frame.empty:
        return None, (
            "near_money could not load the last daily close; strikes were not centered."
        )
    close = frame["Close"].iloc[-1]
    try:
        return float(close), None
    except (TypeError, ValueError):
        return None, (
            "near_money could not load the last daily close; strikes were not centered."
        )


def _strike(row: dict[str, object]) -> float | None:
    value = row.get("strike")
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _filter_strikes(
    rows: list[dict[str, object]],
    *,
    strike_min: float | None,
    strike_max: float | None,
    spot: float | None,
) -> tuple[list[dict[str, object]], str | None]:
    kept: list[dict[str, object]] = []
    bounded: list[dict[str, object]] = []
    for row in rows:
        strike = _strike(row)
        if strike is None:
            continue
        if strike_min is not None and strike < strike_min:
            continue
        if strike_max is not None and strike > strike_max:
            continue
        bounded.append(row)
        if spot is not None and spot != 0.0:
            if abs(strike - spot) / abs(spot) > _NEAR_MONEY_BAND:
                continue
        kept.append(row)
    if spot is not None and not kept and bounded:
        ordered = sorted(bounded, key=lambda row: abs((_strike(row) or 0.0) - spot))
        return ordered, (
            "near_money window was empty; returned the closest strikes instead."
        )
    return kept, None


def _cap(
    rows: list[dict[str, object]],
    limit: int,
    spot: float | None,
) -> tuple[list[dict[str, object]], bool]:
    if spot is not None:
        ordered = sorted(rows, key=lambda row: abs((_strike(row) or 0.0) - spot))
        chosen = ordered[:limit]
        chosen.sort(key=lambda row: _strike(row) or 0.0)
    else:
        ordered = sorted(rows, key=lambda row: _strike(row) or 0.0)
        chosen = ordered[:limit]
    return chosen, len(rows) > len(chosen)
