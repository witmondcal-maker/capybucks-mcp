from __future__ import annotations

import os

import httpx
import pytest
from capybucks.core.http import _raise_status
from capybucks.exceptions import (
    MissingAPIKey,
    NoProviderError,
    ProviderError,
    ProviderNotFound,
    RateLimitError,
    StreamingNotSupportedError,
    SymbolNotFound,
)
from capybucks.providers.coingecko import to_coingecko_id

from capybucks_mcp.catalog import MAPPED_COINGECKO_SYMBOLS
from capybucks_mcp.config import normalize_process_env
from capybucks_mcp.envelope import dumps, enforce_size, success
from capybucks_mcp.errors import describe_error, failure_envelope
from capybucks_mcp.guard import CooldownActive, Guard
from capybucks_mcp.scrub import scrub
from capybucks_mcp.serialize import truncation
from capybucks_mcp.ttl_cache import TTLCache


def test_phase0_http_404_stays_provider_error() -> None:
    """Yahoo answers 404 for an unknown symbol. The library does not remap it."""
    response = httpx.Response(404)
    with pytest.raises(ProviderError) as caught:
        _raise_status(response, provider="yahoo")
    assert type(caught.value) is ProviderError
    payload = failure_envelope("get_history", ProviderError("yahoo HTTP 404"))
    error = payload["error"]
    assert isinstance(error, dict)
    assert error["code"] == "provider_error"
    assert error["code"] != "symbol_not_found"


def test_phase0_unmapped_coingecko_ids() -> None:
    for symbol in MAPPED_COINGECKO_SYMBOLS:
        assert to_coingecko_id(symbol) != symbol.lower()
    for symbol in ("DOGE", "XRP", "ADA", "SOLUSD"):
        assert to_coingecko_id(symbol) == symbol.lower()


def test_error_table(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAPYBUCKS_TWELVEDATA_KEY", "sk-test-123")
    cases: list[tuple[BaseException, str, bool]] = [
        (SymbolNotFound("PETR4", provider="yahoo"), "symbol_not_found", False),
        (MissingAPIKey("twelvedata"), "missing_api_key", False),
        (RateLimitError("yahoo rejected the request (403)"), "rate_limited", True),
        (ProviderError("yahoo HTTP 404"), "provider_error", False),
        (ProviderError("yahoo HTTP 503"), "provider_error", True),
        (ProviderError("stooq returned a bot-check page"), "provider_error", True),
        (ProviderNotFound("nope"), "unknown_provider", False),
        (NoProviderError(asset_type="fx", interval="1d"), "no_provider", False),
        (StreamingNotSupportedError("yahoo"), "streaming_unsupported", False),
        (
            NotImplementedError("coingecko does not implement options"),
            "unsupported_capability",
            False,
        ),
        (ValueError("unknown period ' fortnight'"), "invalid_argument", False),
        (ImportError("calendars extra"), "missing_extra", False),
        (httpx.ConnectError("apikey=sk-test-123"), "network_error", True),
        (TimeoutError("timed out"), "network_error", True),
        (CooldownActive("yahoo", 30), "rate_limited", True),
        (RuntimeError("boom sk-test-123"), "internal_error", False),
    ]
    for exc, code, retryable in cases:
        error = describe_error(exc, provider="yahoo", capability="options")
        assert error["code"] == code
        assert error["retryable"] is retryable
        blob = dumps({"ok": False, "error": error})
        assert "sk-test-123" not in blob
        assert "apikey=[redacted]" in blob or "apikey=" not in blob


def test_symbol_not_found_hint() -> None:
    error = describe_error(SymbolNotFound("PETR4", provider="yahoo"))
    details = error["details"]
    assert isinstance(details, dict)
    assert details["hint"] == "PETR4.SA"
    assert error["next_step"] == "Tell the user, then retry with symbol=PETR4.SA."


def test_scrub_removes_key_and_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAPYBUCKS_TWELVEDATA_KEY", "sk-test-123")
    text = "url https://api.twelvedata.com/quote?apikey=sk-test-123&symbol=AAPL"
    cleaned = scrub(text)
    assert "sk-test-123" not in cleaned
    assert "apikey=[redacted]" in cleaned


def test_placeholder_and_blank_env_are_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAPYBUCKS_TWELVEDATA_KEY", "${CAPYBUCKS_TWELVEDATA_KEY}")
    normalize_process_env()
    assert "CAPYBUCKS_TWELVEDATA_KEY" not in os.environ
    monkeypatch.setenv("CAPYBUCKS_TWELVEDATA_KEY", "   ")
    normalize_process_env()
    assert "CAPYBUCKS_TWELVEDATA_KEY" not in os.environ
    monkeypatch.setenv("CAPYBUCKS_TWELVEDATA_KEY", "real-key-value")
    normalize_process_env()
    assert os.environ["CAPYBUCKS_TWELVEDATA_KEY"] == "real-key-value"


@pytest.mark.asyncio
async def test_guard_cooldown_semaphore_and_timeout() -> None:
    guard = Guard(concurrency=1, timeout=0.05, cooldown=30)
    calls = {"n": 0}

    async def boom() -> None:
        calls["n"] += 1
        raise RateLimitError("yahoo rate-limited this client")

    with pytest.raises(RateLimitError):
        await guard.run("yahoo", boom)
    with pytest.raises(CooldownActive):
        await guard.run("yahoo", boom)
    assert calls["n"] == 1

    async def slow() -> str:
        import asyncio

        await asyncio.sleep(1)
        return "late"

    with pytest.raises(TimeoutError):
        await guard.run("stooq", slow)

    order: list[str] = []

    async def step(label: str) -> str:
        import asyncio

        order.append(f"start-{label}")
        await asyncio.sleep(0.02)
        order.append(f"end-{label}")
        return label

    wide = Guard(concurrency=1, timeout=2, cooldown=30)
    import asyncio

    await asyncio.gather(
        wide.run("yahoo", lambda: step("a")), wide.run("yahoo", lambda: step("b"))
    )
    assert order.index("end-a") < order.index("start-b") or order.index(
        "end-b"
    ) < order.index("start-a")


def test_ttl_cache_expires_and_zero_disables() -> None:
    import time

    cache = TTLCache()
    cache.put("quote", {"price": 1}, 0.01)
    assert cache.get("quote") == {"price": 1}
    time.sleep(0.02)
    assert cache.get("quote") is None
    cache.put("quote", {"price": 2}, 0)
    assert cache.get("quote") is None


def test_enforce_size_marks_truncation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("capybucks_mcp.envelope.max_json_bytes", lambda: 350)
    rows = [{"date": f"2024-01-{index:02d}", "close": index} for index in range(1, 28)]
    payload = success(
        tool="get_history",
        data={"rows": rows},
        truncation=truncation(len(rows), len(rows)),
    )
    shrunk = enforce_size(payload)
    data = shrunk["data"]
    trunc = shrunk["truncation"]
    assert isinstance(data, dict)
    assert isinstance(trunc, dict)
    assert trunc["truncated"] is True
    kept = data.get("rows")
    if data.get("omitted") is True:
        assert trunc["rows_returned"] == 0
    else:
        assert isinstance(kept, list)
        assert len(kept) < len(rows)
