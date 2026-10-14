"""``compute_indicators``."""

from __future__ import annotations

from typing import Literal, cast

import pandas as pd
from capybucks import ta

from capybucks_mcp.envelope import YAHOO_WARNING, success
from capybucks_mcp.errors import failure_envelope
from capybucks_mcp.runtime import fetch_history
from capybucks_mcp.serialize import columnar, provenance_from_frame, round6, truncation
from capybucks_mcp.validate import (
    INDICATORS,
    check_interval,
    check_period,
    check_window,
    clamp_last_n,
    parse_symbol,
)


async def compute_indicators(
    symbol: str,
    indicators: list[Literal["sma", "ema", "rsi", "macd", "bollinger", "atr", "vwap"]]
    | None = None,
    period: str = "6mo",
    interval: str = "1d",
    provider: Literal["yahoo", "coingecko", "stooq", "twelvedata"] | None = None,
    window: int = 20,
    rsi_window: int = 14,
    atr_window: int = 14,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    bands_std: float = 2.0,
    last_n: int | None = None,
) -> dict[str, object]:
    try:
        parsed = parse_symbol(symbol)
        chosen = [str(name) for name in indicators] if indicators else ["sma", "rsi"]
        unknown = [name for name in chosen if name not in INDICATORS]
        if unknown:
            raise ValueError(
                f"unknown indicators {unknown!r}; "
                f"expected names from {sorted(INDICATORS)}"
            )
        if not chosen:
            raise ValueError("at least one indicator is required")
        check_period(period)
        check_interval(interval, provider)
        check_window("window", window)
        check_window("rsi_window", rsi_window)
        check_window("atr_window", atr_window)
        check_window("macd_fast", macd_fast)
        check_window("macd_slow", macd_slow)
        check_window("macd_signal", macd_signal)
        if macd_fast >= macd_slow:
            raise ValueError("macd_fast must be lower than macd_slow")
        if bands_std <= 0:
            raise ValueError("bands_std must be > 0")
        limit = clamp_last_n(last_n)
        frame, name = await fetch_history(
            parsed,
            period=period,
            interval=interval,
            start=None,
            end=None,
            auto_adjust=True,
            provider=provider,
            use_cache=True,
        )
        provenance = provenance_from_frame(frame)
        warnings = _warmup_warnings(
            chosen,
            window=window,
            rsi_window=rsi_window,
            atr_window=atr_window,
            macd_slow=macd_slow,
            macd_signal=macd_signal,
            rows=int(len(frame)),
        )
        if name == "yahoo":
            warnings.append(YAHOO_WARNING)
            warnings.append(
                "Close is the adjusted close because auto_adjust is true (Yahoo)."
            )
        table = _build(
            frame,
            chosen,
            window=window,
            rsi_window=rsi_window,
            atr_window=atr_window,
            macd_fast=macd_fast,
            macd_slow=macd_slow,
            macd_signal=macd_signal,
            bands_std=bands_std,
            null_vwap=name == "coingecko",
        )
        if name == "coingecko" and "vwap" in chosen:
            warnings.append("volume not provided by source; vwap is null")
        total = int(len(table))
        view = table.tail(limit)
        columns = [column for column in view.columns if column != "date"]
        packed = columnar(view, columns)
        return success(
            tool="compute_indicators",
            data={
                "symbol": parsed,
                "indicator_params": {
                    "indicators": chosen,
                    "window": window,
                    "rsi_window": rsi_window,
                    "atr_window": atr_window,
                    "macd_fast": macd_fast,
                    "macd_slow": macd_slow,
                    "macd_signal": macd_signal,
                    "bands_std": bands_std,
                },
                "columns": packed["columns"],
                "rows": packed["rows"],
            },
            provenance=provenance,
            truncation=truncation(total, int(len(view))),
            warnings=warnings,
        )
    except Exception as exc:
        return failure_envelope("compute_indicators", exc)


def _warmup_warnings(
    chosen: list[str],
    *,
    window: int,
    rsi_window: int,
    atr_window: int,
    macd_slow: int,
    macd_signal: int,
    rows: int,
) -> list[str]:
    notes = {
        "sma": window,
        "ema": window,
        "bollinger": window,
        "rsi": rsi_window,
        "atr": atr_window,
        "macd": macd_slow + macd_signal,
    }
    warnings: list[str] = []
    for name in chosen:
        minimum = notes.get(name)
        if minimum is None:
            continue
        warnings.append(
            f"{name}: rows before the window are null (minimum bars about {minimum})."
        )
        if rows < minimum:
            warnings.append(
                f"{name}: the series has {rows} bars, fewer than the window, "
                "so values are null."
            )
    warnings.append(
        "Indicators are textbook formulas rounded to 6 decimals, not a trading system."
    )
    return warnings


def _build(
    frame: pd.DataFrame,
    chosen: list[str],
    *,
    window: int,
    rsi_window: int,
    atr_window: int,
    macd_fast: int,
    macd_slow: int,
    macd_signal: int,
    bands_std: float,
    null_vwap: bool,
) -> pd.DataFrame:
    close = cast(pd.Series, frame["Close"].astype(float))
    high = cast(pd.Series, frame["High"].astype(float))
    low = cast(pd.Series, frame["Low"].astype(float))
    volume = cast(pd.Series, frame["Volume"].astype(float))
    columns: dict[str, pd.Series] = {"close": close}
    if "sma" in chosen:
        columns["sma"] = ta.sma(close, window)
    if "ema" in chosen:
        columns["ema"] = ta.ema(close, window)
    if "rsi" in chosen:
        columns["rsi"] = ta.rsi(close, rsi_window)
    if "macd" in chosen:
        macd_frame = ta.macd(close, fast=macd_fast, slow=macd_slow, signal=macd_signal)
        columns["macd"] = macd_frame["macd"]
        columns["macd_signal"] = macd_frame["signal"]
        columns["macd_histogram"] = macd_frame["histogram"]
    if "bollinger" in chosen:
        bands = ta.bollinger(close, window=window, num_std=bands_std)
        columns["bb_mid"] = bands["mid"]
        columns["bb_upper"] = bands["upper"]
        columns["bb_lower"] = bands["lower"]
    if "atr" in chosen:
        columns["atr"] = ta.atr(high, low, close, window=atr_window)
    if "vwap" in chosen:
        if null_vwap:
            columns["vwap"] = pd.Series(
                [float("nan")] * len(frame), index=frame.index, dtype="float64"
            )
        else:
            columns["vwap"] = ta.vwap(high, low, close, volume)
    table = pd.DataFrame(columns)
    for column in table.columns:
        if column == "close":
            continue
        table[column] = table[column].map(round6)
    return table
