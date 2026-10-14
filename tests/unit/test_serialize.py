from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from capybucks_mcp.serialize import (
    json_cell,
    ohlcv_rows,
    provenance_from_frame,
    summary_payload,
    take_recent,
)


def _frame() -> pd.DataFrame:
    index = pd.DatetimeIndex(
        [
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2024, 1, 2, tzinfo=UTC),
            datetime(2024, 1, 3, tzinfo=UTC),
        ],
        name="Date",
    )
    frame = pd.DataFrame(
        {
            "Open": [10.0, 11.0, 12.0],
            "High": [11.0, 12.0, 13.0],
            "Low": [9.0, 10.0, 11.0],
            "Close": [10.0, float("nan"), 12.0],
            "Adj Close": [10.0, 11.0, 12.0],
            "Volume": [1.0, 2.0, None],
        },
        index=index,
    )
    frame.attrs["provider"] = "yahoo"
    frame.attrs["delayed"] = True
    frame.attrs["adjustment"] = "split_and_dividend"
    frame.attrs["asof"] = datetime(2024, 1, 3, 12, 0, tzinfo=UTC)
    frame.attrs["currency"] = "USD"
    return frame


def test_nan_and_nat_become_null() -> None:
    assert json_cell(float("nan")) is None
    assert json_cell(float("inf")) is None
    assert json_cell(pd.NaT) is None
    assert json_cell(pd.Timestamp("NaT")) is None


def test_attrs_captured_before_tail() -> None:
    frame = _frame()
    provenance = provenance_from_frame(frame)
    view, trunc = take_recent(frame, 1)
    assert provenance["provider"] == "yahoo"
    assert provenance["asof"] == "2024-01-03T12:00:00+00:00"
    assert provenance["timezone"] == "UTC"
    assert trunc["rows_total"] == 3
    assert trunc["rows_returned"] == 1
    assert trunc["truncated"] is True
    assert len(view) == 1
    rows = ohlcv_rows(view, null_volume=False)
    assert rows[0]["close"] is None or rows[0]["date"] == "2024-01-03T00:00:00+00:00"
    assert rows[0]["volume"] is None


def test_snake_case_rows_and_coingecko_volume() -> None:
    frame = _frame()
    rows = ohlcv_rows(frame, null_volume=True)
    assert set(rows[0]) == {
        "date",
        "open",
        "high",
        "low",
        "close",
        "adj_close",
        "volume",
    }
    assert rows[0]["volume"] is None
    assert rows[1]["close"] is None


def test_summary_change_pct_is_handmade() -> None:
    index = pd.DatetimeIndex(
        [datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 1, 2, tzinfo=UTC)],
        name="Date",
    )
    frame = pd.DataFrame(
        {
            "Open": [100.0, 110.0],
            "High": [120.0, 130.0],
            "Low": [90.0, 100.0],
            "Close": [100.0, 110.0],
            "Adj Close": [100.0, 110.0],
            "Volume": [10.0, 30.0],
        },
        index=index,
    )
    summary, _trunc = summary_payload(frame, null_volume=False)
    assert summary["change_pct"] == 10.0
    assert summary["high_max"] == 130.0
    assert summary["low_min"] == 90.0
    assert summary["avg_volume"] == 20.0
    assert summary["count"] == 2
    tail = summary["tail"]
    assert isinstance(tail, list)
    assert len(tail) == 2
