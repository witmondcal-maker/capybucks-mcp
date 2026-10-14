"""Success and error envelopes shared by every tool."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

from capybucks_mcp.config import max_json_bytes
from capybucks_mcp.scrub import scrub

NOTICE = (
    "Informational data. May be delayed and may come from unofficial sources. "
    "Not investment advice. Read-only; this server does not place orders."
)

YAHOO_WARNING = (
    "Yahoo Finance is not an official API (query1.finance.yahoo.com). "
    "It may change or stop without notice, and Yahoo's terms restrict "
    "automated collection. Do not redistribute provider data."
)

QUOTE_WARNING = (
    "Yahoo and CoinGecko quotes are the last daily bar, not a live price. "
    "Twelve Data stamps timestamp with the time of the call, not the trade time."
)

UNMAPPED_COINGECKO = (
    "Only BTC, ETH and SOL (plus BTC-USD, ETH-USD, SOL-USD, BTCUSD and ETHUSD) "
    "have a mapped CoinGecko id. Other symbols are sent as the lowercased ticker "
    "and can resolve to a different asset."
)

DELAY_UNKNOWN = (
    "Delay is not reported by the source for this dataset. "
    "Do not present these figures as real time."
)

SUMMARY_NOTE = (
    "Summary statistics are computed by the server from the Close column "
    "(adjusted when auto_adjust is true), not supplied by the provider."
)

HYPHEN_WARNING = (
    "Symbols with '-' are treated as crypto; "
    "pass provider=yahoo for tickers like BRK-B."
)

_SHRINK_KEYS = frozenset({"rows", "calls", "puts", "tail"})


def dedupe(warnings: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in warnings:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def success(
    *,
    tool: str,
    data: dict[str, object],
    provenance: dict[str, object] | None = None,
    truncation: dict[str, object] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "ok": True,
        "tool": tool,
        "data": data,
        "warnings": dedupe(list(warnings or [])),
        "notice": NOTICE,
    }
    if provenance is not None:
        body["provenance"] = provenance
    if truncation is not None:
        body["truncation"] = truncation
    return body


def failure(
    *,
    tool: str,
    error: dict[str, object],
    warnings: list[str] | None = None,
) -> dict[str, object]:
    return {
        "ok": False,
        "tool": tool,
        "error": error,
        "warnings": dedupe(list(warnings or [])),
        "notice": NOTICE,
    }


def dumps(payload: Mapping[str, object]) -> str:
    """Serialize an envelope. ``NaN`` is rejected; secrets are redacted."""
    text = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    return scrub(text)


def _nbytes(payload: Mapping[str, object]) -> int:
    return len(dumps(payload).encode("utf-8"))


def _warnings(payload: dict[str, object]) -> list[str]:
    current = payload.get("warnings")
    if isinstance(current, list):
        warnings = [item for item in current if isinstance(item, str)]
    else:
        warnings = []
    payload["warnings"] = warnings
    return warnings


def _collect_lists(node: object, found: list[list[object]]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _SHRINK_KEYS and isinstance(value, list) and len(value) > 1:
                found.append(cast(list[object], value))
            else:
                _collect_lists(value, found)
    elif isinstance(node, list):
        for item in node:
            _collect_lists(item, found)


def _sync_truncation(payload: dict[str, object]) -> None:
    data = payload.get("data")
    if not isinstance(data, dict):
        return
    rows = data.get("rows")
    trunc = payload.get("truncation")
    if isinstance(rows, list) and isinstance(trunc, dict):
        trunc["truncated"] = True
        trunc["rows_returned"] = len(rows)
    series = data.get("series")
    if isinstance(series, dict):
        for entry in series.values():
            if not isinstance(entry, dict):
                continue
            entry_rows = entry.get("rows")
            entry_trunc = entry.get("truncation")
            if isinstance(entry_rows, list) and isinstance(entry_trunc, dict):
                entry_trunc["truncated"] = True
                entry_trunc["rows_returned"] = len(entry_rows)


def enforce_size(payload: dict[str, object]) -> dict[str, object]:
    """Drop the oldest returned rows until the JSON fits in the size cap."""
    limit = max_json_bytes()
    if _nbytes(payload) <= limit:
        return payload
    warnings = _warnings(payload)
    warnings.append(
        "Response exceeded the 60KB cap; older rows were dropped "
        "and truncation was marked."
    )
    for _ in range(16):
        lists: list[list[object]] = []
        _collect_lists(payload.get("data"), lists)
        if not lists:
            break
        target = max(lists, key=len)
        if len(target) <= 1:
            break
        keep = max(1, len(target) // 2)
        del target[: len(target) - keep]
        _sync_truncation(payload)
        if _nbytes(payload) <= limit:
            return payload
    payload["data"] = {"omitted": True}
    payload["truncation"] = {
        "rows_total": None,
        "rows_returned": 0,
        "truncated": True,
        "kept": "most_recent",
    }
    warnings.append(
        "Response still exceeded the cap after shrinking; data was omitted."
    )
    return payload
