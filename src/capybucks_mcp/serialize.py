"""Turn DataFrames and provider models into JSON-safe structures."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime

import numpy as np
import pandas as pd

from capybucks_mcp.validate import clamp_history_rows

OHLCV_COLUMNS = ["date", "open", "high", "low", "close", "adj_close", "volume"]

_OPTION_FIELDS = (
    ("contractSymbol", "contract_symbol"),
    ("strike", "strike"),
    ("lastPrice", "last_price"),
    ("bid", "bid"),
    ("ask", "ask"),
    ("volume", "volume"),
    ("openInterest", "open_interest"),
    ("impliedVolatility", "implied_volatility"),
    ("inTheMoney", "in_the_money"),
)


def isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _missing(value: object) -> bool:
    """True for ``NaN``, ``NaT`` and infinities. Arrays return False.

    ``pd.NaT`` is a ``datetime`` subclass, so identity is checked before
    ``isinstance(..., datetime)`` in ``json_cell``. ``pd.Timestamp("NaT")``
    is that same singleton.
    """
    if value is pd.NaT or value is pd.NA:
        return True
    if isinstance(value, float):
        return math.isnan(value) or math.isinf(value)
    if isinstance(value, np.floating):
        number = float(value)
        return math.isnan(number) or math.isinf(number)
    return False


def json_cell(value: object) -> object:
    """Convert one cell. ``NaN``, ``NaT`` and infinities become ``None``."""
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return value
    if _missing(value):
        return None
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, datetime):
        return isoformat(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    if isinstance(value, pd.Timestamp):
        return isoformat(value.to_pydatetime())
    return None


def round6(value: object) -> float | None:
    cell = json_cell(value)
    if isinstance(cell, bool) or not isinstance(cell, int | float):
        return None
    return round(float(cell), 6)


def provenance_from_frame(frame: pd.DataFrame) -> dict[str, object]:
    """Read provenance before any ``tail`` or ``reset_index``.

    pandas does not always keep ``DataFrame.attrs`` across those operations.
    """
    attrs = dict(frame.attrs)
    asof = attrs.get("asof")
    asof_text = isoformat(asof) if isinstance(asof, datetime) else None
    timezone: str | None = None
    index_tz = getattr(frame.index, "tz", None)
    if index_tz is not None:
        timezone = str(index_tz)
    return {
        "provider": attrs.get("provider"),
        "delayed": attrs.get("delayed"),
        "adjustment": attrs.get("adjustment"),
        "asof": asof_text,
        "currency": attrs.get("currency"),
        "timezone": timezone,
    }


def thin_provenance(provider: str) -> dict[str, object]:
    """Provenance for datasets that do not carry ``df.attrs``."""
    return {"provider": provider}


def truncation(
    total: int, returned: int, *, truncated: bool | None = None
) -> dict[str, object]:
    flag = total > returned if truncated is None else truncated
    return {
        "rows_total": total,
        "rows_returned": returned,
        "truncated": flag,
        "kept": "most_recent",
    }


def ohlcv_rows(frame: pd.DataFrame, *, null_volume: bool) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for label, row in frame.iterrows():
        volume = None if null_volume else json_cell(row["Volume"])
        rows.append(
            {
                "date": json_cell(label),
                "open": json_cell(row["Open"]),
                "high": json_cell(row["High"]),
                "low": json_cell(row["Low"]),
                "close": json_cell(row["Close"]),
                "adj_close": json_cell(row["Adj Close"]),
                "volume": volume,
            }
        )
    return rows


def take_recent(
    frame: pd.DataFrame, max_rows: int | None
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Keep the most recent rows. Capture ``attrs`` before calling this."""
    limit = clamp_history_rows(max_rows)
    total = int(len(frame))
    if total > limit:
        view = frame.tail(limit)
    else:
        view = frame
    return view, truncation(total, int(len(view)))


def summary_payload(
    frame: pd.DataFrame, *, null_volume: bool
) -> tuple[dict[str, object], dict[str, object]]:
    """Stats over the full series, plus the last five rows."""
    close = frame["Close"]
    first = json_cell(close.iloc[0])
    last = json_cell(close.iloc[-1])
    change: float | None = None
    if (
        isinstance(first, int | float)
        and isinstance(last, int | float)
        and not isinstance(first, bool)
    ):
        if float(first) != 0.0:
            change = (float(last) - float(first)) / float(first) * 100.0
    if null_volume:
        avg_volume: float | None = None
    else:
        avg_cell = json_cell(frame["Volume"].mean())
        avg_volume = (
            float(avg_cell)
            if isinstance(avg_cell, int | float) and not isinstance(avg_cell, bool)
            else None
        )
    tail_frame = frame.tail(5)
    tail = ohlcv_rows(tail_frame, null_volume=null_volume)
    summary: dict[str, object] = {
        "count": int(len(frame)),
        "first_date": json_cell(frame.index[0]),
        "last_date": json_cell(frame.index[-1]),
        "first_close": first,
        "last_close": last,
        "change_pct": change,
        "high_max": json_cell(frame["High"].max()),
        "low_min": json_cell(frame["Low"].min()),
        "avg_volume": avg_volume,
        "tail": tail,
        "stats_note": "computed by the server from the Close column",
    }
    return summary, truncation(int(len(frame)), len(tail))


def statement_payload(
    frame: pd.DataFrame,
    *,
    items: list[str] | None,
    max_periods: int,
) -> tuple[list[object], dict[str, list[object]], bool]:
    """Return periods, item rows, and whether the filter matched nothing.

    Item names stay as the provider wrote them. All-null items are dropped.
    """
    working = frame.copy()
    if items:
        wanted = {item.casefold() for item in items}
        keep = [idx for idx in working.index if str(idx).casefold() in wanted]
        working = working.loc[keep]
        if working.empty:
            return [], {}, True
    working = _sort_periods(working)
    if len(working.columns) > max_periods:
        working = working.iloc[:, -max_periods:]
    periods: list[object] = [json_cell(column) for column in working.columns]
    kept: dict[str, list[object]] = {}
    for name, row in working.iterrows():
        values = [json_cell(cell) for cell in row.tolist()]
        if all(value is None for value in values):
            continue
        kept[str(name)] = values
        if len(kept) >= 60:
            break
    return periods, kept, False


def _sort_periods(frame: pd.DataFrame) -> pd.DataFrame:
    columns = list(frame.columns)

    def sort_key(column: object) -> tuple[int, str]:
        cell = json_cell(column)
        if isinstance(cell, str):
            return (0, cell)
        return (1, "")

    ordered = sorted(columns, key=sort_key)
    return frame.reindex(columns=ordered)


def option_rows(frame: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if frame.empty:
        return rows
    ordered = frame.sort_values("strike") if "strike" in frame.columns else frame
    for _, row in ordered.iterrows():
        item: dict[str, object] = {}
        for source, target in _OPTION_FIELDS:
            if source not in ordered.columns:
                item[target] = None
                continue
            cell = json_cell(row[source])
            item[target] = cell
        rows.append(item)
    return rows


def news_items(frame: pd.DataFrame, limit: int) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    view = frame.head(limit)
    for _, row in view.iterrows():
        items.append(
            {
                "title": json_cell(row["title"]) if "title" in view.columns else None,
                "publisher": json_cell(row["publisher"])
                if "publisher" in view.columns
                else None,
                "link": json_cell(row["link"]) if "link" in view.columns else None,
                "published_at": (
                    json_cell(row["published_at"])
                    if "published_at" in view.columns
                    else None
                ),
            }
        )
    return items


def action_rows(
    frame: pd.DataFrame, *, column: str, since: datetime | None
) -> list[dict[str, object]]:
    if frame.empty or column not in frame.columns:
        return []
    rows: list[dict[str, object]] = []
    series = frame[column]
    series = series[series != 0]
    for label, value in series.items():
        when = label
        if isinstance(when, pd.Timestamp):
            if bool(pd.isna(when)):
                continue
            stamp = when.to_pydatetime()
        elif isinstance(when, datetime):
            stamp = when
        else:
            continue
        aware = stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=UTC)
        if since is not None and aware < since:
            continue
        number = json_cell(value)
        if not isinstance(number, int | float) or isinstance(number, bool):
            continue
        if column == "Dividends":
            rows.append({"date": isoformat(aware), "amount": float(number)})
        else:
            rows.append({"date": isoformat(aware), "ratio": float(number)})
    return rows


def columnar(frame: pd.DataFrame, columns: list[str]) -> dict[str, object]:
    """Columnar table. Indicator columns are already rounded; ``close`` is not."""
    rows: list[list[object]] = []
    for label, row in frame.iterrows():
        values: list[object] = [json_cell(label)]
        for column in columns:
            cell = row[column] if column in frame.columns else None
            if column == "close":
                values.append(json_cell(cell))
            else:
                values.append(round6(cell))
        rows.append(values)
    return {"columns": ["date", *columns], "rows": rows}
