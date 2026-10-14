"""``get_history`` and ``get_quote``."""

from __future__ import annotations

from typing import Literal

from capybucks_mcp.envelope import (
    HYPHEN_WARNING,
    QUOTE_WARNING,
    SUMMARY_NOTE,
    UNMAPPED_COINGECKO,
    YAHOO_WARNING,
    success,
)
from capybucks_mcp.errors import failure_envelope
from capybucks_mcp.runtime import fetch_history, fetch_quote
from capybucks_mcp.serialize import (
    OHLCV_COLUMNS,
    isoformat,
    ohlcv_rows,
    provenance_from_frame,
    summary_payload,
    take_recent,
)
from capybucks_mcp.ttl_cache import get_ttl_cache
from capybucks_mcp.validate import (
    check_interval,
    check_period,
    coingecko_unmapped,
    parse_datetime,
    parse_symbol,
    parse_symbols,
)


def _warnings_for(
    symbols: list[str], provider: str | None, resolved: set[str]
) -> list[str]:
    warnings: list[str] = []
    if provider is None and any("-" in symbol for symbol in symbols):
        warnings.append(HYPHEN_WARNING)
    if "yahoo" in resolved:
        warnings.append(YAHOO_WARNING)
    if "coingecko" in resolved and any(
        coingecko_unmapped(symbol) for symbol in symbols
    ):
        warnings.append(UNMAPPED_COINGECKO)
    return warnings


def _quote_kind(provider: str) -> str:
    if provider in {"yahoo", "coingecko"}:
        return "last_daily_bar"
    return "provider_quote"


async def get_history(
    symbols: str | list[str],
    period: str = "1mo",
    interval: str = "1d",
    start: str | None = None,
    end: str | None = None,
    auto_adjust: bool = True,
    provider: Literal["yahoo", "coingecko", "stooq", "twelvedata"] | None = None,
    view: Literal["rows", "summary"] = "rows",
    max_rows: int | None = None,
    use_cache: bool = True,
) -> dict[str, object]:
    warnings: list[str] = []
    try:
        parsed = parse_symbols(symbols)
        check_period(period)
        check_interval(interval, provider)
        start_dt = parse_datetime(start)
        end_dt = parse_datetime(end)
        if provider is None and any("-" in symbol for symbol in parsed):
            warnings.append(HYPHEN_WARNING)
        if len(parsed) == 1:
            return await _one(
                parsed[0],
                period=period,
                interval=interval,
                start=start_dt,
                end=end_dt,
                auto_adjust=auto_adjust,
                provider=provider,
                view=view,
                max_rows=max_rows,
                use_cache=use_cache,
                warnings=warnings,
            )
        return await _many(
            parsed,
            period=period,
            interval=interval,
            start=start_dt,
            end=end_dt,
            auto_adjust=auto_adjust,
            provider=provider,
            view=view,
            max_rows=max_rows,
            use_cache=use_cache,
            warnings=warnings,
        )
    except Exception as exc:
        return failure_envelope("get_history", exc, extra_warnings=warnings)


async def _one(
    symbol: str,
    *,
    period: str,
    interval: str,
    start: object,
    end: object,
    auto_adjust: bool,
    provider: str | None,
    view: str,
    max_rows: int | None,
    use_cache: bool,
    warnings: list[str],
) -> dict[str, object]:
    from datetime import datetime

    start_dt = start if isinstance(start, datetime) else None
    end_dt = end if isinstance(end, datetime) else None
    frame, name = await fetch_history(
        symbol,
        period=period,
        interval=interval,
        start=start_dt,
        end=end_dt,
        auto_adjust=auto_adjust,
        provider=provider,
        use_cache=use_cache,
    )
    provenance = provenance_from_frame(frame)
    warnings.extend(_warnings_for([symbol], provider, {name}))
    if auto_adjust and name == "yahoo":
        warnings.append(
            "Close is the adjusted close because auto_adjust is true (Yahoo)."
        )
    null_volume = name == "coingecko"
    if null_volume:
        warnings.append("volume not provided by source")
    if view == "summary":
        summary, trunc = summary_payload(frame, null_volume=null_volume)
        warnings.append(SUMMARY_NOTE)
        data: dict[str, object] = {"symbol": symbol, "summary": summary}
    else:
        view_frame, trunc = take_recent(frame, max_rows)
        rows = ohlcv_rows(view_frame, null_volume=null_volume)
        data = {"symbol": symbol, "columns": list(OHLCV_COLUMNS), "rows": rows}
    return success(
        tool="get_history",
        data=data,
        provenance=provenance,
        truncation=trunc,
        warnings=warnings,
    )


async def _many(
    symbols: list[str],
    *,
    period: str,
    interval: str,
    start: object,
    end: object,
    auto_adjust: bool,
    provider: str | None,
    view: str,
    max_rows: int | None,
    use_cache: bool,
    warnings: list[str],
) -> dict[str, object]:
    import asyncio

    async def _run(symbol: str) -> tuple[str, dict[str, object] | Exception]:
        try:
            payload = await _one(
                symbol,
                period=period,
                interval=interval,
                start=start,
                end=end,
                auto_adjust=auto_adjust,
                provider=provider,
                view=view,
                max_rows=max_rows,
                use_cache=use_cache,
                warnings=[],
            )
            return symbol, payload
        except Exception as exc:
            return symbol, exc

    gathered = await asyncio.gather(*[_run(symbol) for symbol in symbols])
    series: dict[str, object] = {}
    errors: dict[str, object] = {}
    resolved: set[str] = set()
    rows_total = 0
    rows_returned = 0
    any_truncated = False
    for symbol, result in gathered:
        if isinstance(result, Exception):
            errors[symbol] = failure_envelope("get_history", result)["error"]
            continue
        data = result["data"]
        provenance = result.get("provenance")
        trunc = result.get("truncation")
        if isinstance(provenance, dict):
            provider_name = provenance.get("provider")
            if isinstance(provider_name, str):
                resolved.add(provider_name)
        if isinstance(trunc, dict):
            total = trunc.get("rows_total")
            returned = trunc.get("rows_returned")
            if isinstance(total, int):
                rows_total += total
            if isinstance(returned, int):
                rows_returned += returned
            if trunc.get("truncated") is True:
                any_truncated = True
        entry: dict[str, object] = {"symbol": symbol}
        if isinstance(data, dict):
            for key in ("columns", "rows", "summary"):
                if key in data:
                    entry[key] = data[key]
        if isinstance(provenance, dict):
            entry["provenance"] = provenance
        if isinstance(trunc, dict):
            entry["truncation"] = trunc
        series[symbol] = entry
    if not series:
        from capybucks_mcp.envelope import failure
        from capybucks_mcp.errors import describe_error

        mapped_errors: dict[str, object] = {}
        for symbol, result in gathered:
            if isinstance(result, Exception):
                mapped_errors[symbol] = describe_error(result)
        names = ", ".join(sorted(mapped_errors))
        return failure(
            tool="get_history",
            error={
                "code": "all_symbols_failed",
                "type": "MultiDownloadError",
                "message": f"download failed for all symbols: {names}",
                "retryable": False,
                "details": {"errors": mapped_errors},
                "next_step": (
                    "Inspect each symbol error. Do not switch providers on your own."
                ),
            },
            warnings=warnings,
        )
    warnings.extend(_warnings_for(symbols, provider, resolved))
    if "coingecko" in resolved:
        warnings.append("volume not provided by source")
    if auto_adjust and "yahoo" in resolved:
        warnings.append(
            "Close is the adjusted close because auto_adjust is true (Yahoo)."
        )
    if view == "summary":
        warnings.append(SUMMARY_NOTE)
    return success(
        tool="get_history",
        data={"series": series, "errors": errors},
        truncation={
            "rows_total": rows_total,
            "rows_returned": rows_returned,
            "truncated": any_truncated,
            "kept": "most_recent",
        },
        warnings=warnings,
    )


async def get_quote(
    symbol: str,
    provider: Literal["yahoo", "coingecko", "stooq", "twelvedata"] | None = None,
) -> dict[str, object]:
    warnings = [QUOTE_WARNING]
    try:
        parsed = parse_symbol(symbol)
        if provider is None and "-" in parsed:
            warnings.append(HYPHEN_WARNING)
        cache_key = f"quote|{provider or ''}|{parsed}"
        cached = get_ttl_cache().get(cache_key)
        if isinstance(cached, tuple) and len(cached) == 2:
            quote, name = cached
        else:
            quote, name = await fetch_quote(parsed, provider)
            get_ttl_cache().put_kind(cache_key, (quote, name), "quote")
        if not hasattr(quote, "price"):
            raise TypeError("quote cache held an unexpected value")
        if name == "yahoo":
            warnings.append(YAHOO_WARNING)
        if name == "coingecko" and coingecko_unmapped(parsed):
            warnings.append(UNMAPPED_COINGECKO)
        provenance = {
            "provider": name,
            "delayed": quote.delayed,
            "asof": isoformat(quote.timestamp),
            "currency": quote.currency,
        }
        data = {
            "symbol": quote.symbol,
            "price": quote.price,
            "timestamp": isoformat(quote.timestamp),
            "currency": quote.currency,
            "delayed": quote.delayed,
            "quote_kind": _quote_kind(name),
        }
        return success(
            tool="get_quote",
            data=data,
            provenance=provenance,
            warnings=warnings,
        )
    except Exception as exc:
        return failure_envelope("get_quote", exc, extra_warnings=warnings)
