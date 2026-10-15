"""HTTP behavior of the real providers, through the tool response."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx
from capybucks.core.config import set_config_path
from tests.conftest import install_market

from capybucks_mcp.tools.fundamentals import get_dividends_and_splits, get_financials
from capybucks_mcp.tools.history import get_history, get_quote
from capybucks_mcp.tools.news import get_news
from capybucks_mcp.tools.options import get_option_expirations

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
TD_KEY = "td-fixture-key-value"
TOML_KEY = "toml-only-secret-value"
WHEN = {
    "start": "2024-01-02T00:00:00+00:00",
    "end": "2024-01-10T00:00:00+00:00",
    "use_cache": False,
}
HOST = {
    "yahoo": r"query1\.finance\.yahoo\.com",
    "coingecko": r"api\.coingecko\.com",
    "stooq": r"stooq\.com",
    "twelvedata": r"api\.twelvedata\.com",
}
PROVIDERS = ("yahoo", "coingecko", "stooq", "twelvedata")
MALICIOUS = (
    "AAPL/../../../v1/test",
    "AAPL\\..\\..\\windows",
    "..",
    "AAPL?x=1",
    "AAPL#frag",
    "AAA\x00BBB",
    "EUR/USD",
)


def _symbol(provider: str) -> str:
    if provider == "coingecko":
        return "BTC-USD"
    return "AAPL"


def _error(payload: dict[str, object]) -> dict[str, object]:
    assert payload["ok"] is False
    error = payload["error"]
    assert isinstance(error, dict)
    blob = json.dumps(payload)
    assert "Traceback (most recent call last)" not in blob
    assert TD_KEY not in blob
    assert TOML_KEY not in blob
    assert isinstance(error["code"], str)
    assert isinstance(error["message"], str)
    assert isinstance(error["retryable"], bool)
    assert isinstance(error["next_step"], str)
    return error


def _route(provider: str) -> respx.Route:
    return respx.get(url__regex=rf"https://{HOST[provider]}/.*")


@pytest.fixture
def td_key(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("CAPYBUCKS_TWELVEDATA_KEY", TD_KEY)
    return TD_KEY


async def _history(provider: str) -> dict[str, object]:
    return await get_history(
        _symbol(provider),
        period="5d",
        provider=provider,
        **WHEN,
    )


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize("symbol", MALICIOUS)
async def test_malicious_symbol_is_rejected_before_http(symbol: str) -> None:
    install_market()
    respx.get(url__regex=r"https://.*").mock(return_value=httpx.Response(200, text="x"))
    payload = await get_history(symbol, provider="yahoo", period="5d", **WHEN)
    error = _error(payload)
    assert error["code"] == "invalid_argument"
    assert error["next_step"] == "Fix the argument and retry."
    urls = [f"{call.request.method} {call.request.url}" for call in respx.calls]
    assert urls == []


@respx.mock
@pytest.mark.asyncio
async def test_legitimate_symbols_stay_on_the_chart_path() -> None:
    install_market()
    chart = json.loads(
        (FIXTURES / "yahoo" / "chart_aapl.json").read_text(encoding="utf-8")
    )
    btc = json.loads(
        (FIXTURES / "coingecko" / "btc_ohlc.json").read_text(encoding="utf-8")
    )
    respx.get(url__regex=r"https://query1\.finance\.yahoo\.com/.*").mock(
        return_value=httpx.Response(200, json=chart)
    )
    respx.get(url__regex=r"https://api\.coingecko\.com/.*").mock(
        return_value=httpx.Response(200, json=btc)
    )
    cases = (
        ("PETR4.SA", "yahoo", "/v8/finance/chart/PETR4.SA"),
        ("BRK-B", "yahoo", "/v8/finance/chart/BRK-B"),
        ("^GSPC", "yahoo", "/v8/finance/chart/%5EGSPC"),
        ("EURUSD=X", "yahoo", "/v8/finance/chart/EURUSD%3DX"),
    )
    for symbol, provider, needle in cases:
        payload = await get_history(symbol, provider=provider, period="5d", **WHEN)
        assert payload["ok"] is True
        data = payload["data"]
        assert isinstance(data, dict)
        assert data["symbol"] == symbol
        url = str(respx.calls[-1].request.url)
        assert needle in url
        assert "/v8/V1/" not in url
        assert respx.calls[-1].request.method == "GET"
    btc_payload = await get_history("BTC-USD", period="5d", **WHEN)
    assert btc_payload["ok"] is True
    btc_data = btc_payload["data"]
    assert isinstance(btc_data, dict)
    assert btc_data["symbol"] == "BTC-USD"
    btc_url = str(respx.calls[-1].request.url)
    assert "/api/v3/coins/bitcoin/ohlc" in btc_url
    assert respx.calls[-1].request.method == "GET"


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize("provider", PROVIDERS)
async def test_http_401(provider: str, td_key: str) -> None:
    install_market()
    route = _route(provider).mock(return_value=httpx.Response(401))
    payload = await _history(provider)
    error = _error(payload)
    assert route.call_count == 1
    blob = json.dumps(payload)
    if provider == "twelvedata":
        assert error["code"] == "missing_api_key"
        details = error["details"]
        assert isinstance(details, dict)
        assert details["env_var"] == "CAPYBUCKS_TWELVEDATA_KEY"
        assert "CAPYBUCKS_TWELVEDATA_KEY" in str(error["next_step"])
        assert td_key not in blob
    else:
        assert error["code"] == "provider_error"
        assert error["retryable"] is False
        assert "CAPYBUCKS_" not in blob
        assert "missing_api_key" not in blob
    if provider == "yahoo":
        assert error["message"] == (
            "Yahoo denied access. Yahoo Finance is not an official API. "
            "Try again later."
        )
        assert error["next_step"] == (
            "Try again later. Do not switch providers on your own."
        )


@respx.mock
@pytest.mark.asyncio
async def test_twelvedata_without_key_asks_for_the_real_variable() -> None:
    install_market()
    route = _route("twelvedata").mock(return_value=httpx.Response(401))
    payload = await _history("twelvedata")
    error = _error(payload)
    assert error["code"] == "missing_api_key"
    details = error["details"]
    assert isinstance(details, dict)
    assert details["env_var"] == "CAPYBUCKS_TWELVEDATA_KEY"
    assert route.call_count == 0
    assert "CAPYBUCKS_YAHOO_KEY" not in json.dumps(payload)


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize("provider", PROVIDERS)
async def test_http_403_is_rate_limited(provider: str, td_key: str) -> None:
    install_market()
    route = _route(provider).mock(return_value=httpx.Response(403))
    payload = await _history(provider)
    error = _error(payload)
    assert error["code"] == "rate_limited"
    assert error["retryable"] is True
    assert route.call_count == 3
    assert td_key not in json.dumps(payload)


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize("provider", PROVIDERS)
async def test_http_429_retries_then_stops_at_three(provider: str, td_key: str) -> None:
    install_market()
    route = _route(provider).mock(return_value=httpx.Response(429))
    payload = await _history(provider)
    error = _error(payload)
    assert error["code"] == "rate_limited"
    assert error["retryable"] is True
    assert route.call_count == 3
    assert "Traceback" not in json.dumps(payload)


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize("provider", PROVIDERS)
async def test_http_5xx(provider: str, td_key: str) -> None:
    install_market()
    route = _route(provider).mock(return_value=httpx.Response(502))
    payload = await _history(provider)
    error = _error(payload)
    assert error["code"] == "provider_error"
    assert error["retryable"] is True
    assert "502" in str(error["message"])
    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize("provider", PROVIDERS)
async def test_http_timeout(provider: str, td_key: str) -> None:
    install_market()

    def explode(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    route = _route(provider).mock(side_effect=explode)
    payload = await _history(provider)
    error = _error(payload)
    assert error["code"] == "network_error"
    assert error["retryable"] is True
    assert error["type"] == "ReadTimeout"
    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize("provider", PROVIDERS)
async def test_invalid_payload_is_provider_error(provider: str, td_key: str) -> None:
    install_market()
    route = _route(provider).mock(
        return_value=httpx.Response(200, text="<html>not json</html>")
    )
    payload = await _history(provider)
    error = _error(payload)
    assert error["code"] == "provider_error"
    assert error["next_step"] != "Fix the argument and retry."
    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize("provider", PROVIDERS)
async def test_missing_field(provider: str, td_key: str) -> None:
    install_market()
    if provider == "yahoo":
        body: object = {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "currency": "USD",
                            "exchangeTimezoneName": "America/New_York",
                        },
                        "timestamp": [1704499200],
                    }
                ],
                "error": None,
            }
        }
        response = httpx.Response(200, json=body)
        expected = "provider_error"
    elif provider == "coingecko":
        response = httpx.Response(200, json={"prices": []})
        expected = "provider_error"
    elif provider == "twelvedata":
        response = httpx.Response(
            200, json={"meta": {"currency": "USD"}, "status": "ok"}
        )
        expected = "provider_error"
    else:
        response = httpx.Response(
            200, text="Date,Open,High,Low,Volume\n2024-01-02,1,2,1,9\n"
        )
        expected = "symbol_not_found"
    route = _route(provider).mock(return_value=response)
    payload = await _history(provider)
    error = _error(payload)
    assert error["code"] == expected
    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize("provider", PROVIDERS)
async def test_empty_list(provider: str, td_key: str) -> None:
    install_market()
    if provider == "yahoo":
        response = httpx.Response(200, json={"chart": {"result": [], "error": None}})
    elif provider == "coingecko":
        response = httpx.Response(200, json=[])
    elif provider == "twelvedata":
        response = httpx.Response(
            200,
            json={
                "meta": {"currency": "USD", "exchange_timezone": "UTC"},
                "values": [],
                "status": "ok",
            },
        )
    else:
        response = httpx.Response(200, text="Date,Open,High,Low,Close,Volume\n")
    route = _route(provider).mock(return_value=response)
    payload = await _history(provider)
    error = _error(payload)
    assert error["code"] == "symbol_not_found"
    assert error["retryable"] is False
    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "expected"),
    (
        ("yahoo", "provider_error"),
        ("coingecko", "provider_error"),
        ("stooq", "symbol_not_found"),
        ("twelvedata", "symbol_not_found"),
    ),
)
async def test_unknown_ticker(provider: str, expected: str, td_key: str) -> None:
    install_market()
    if provider == "yahoo":
        response = httpx.Response(404, text="not found")
    elif provider == "coingecko":
        response = httpx.Response(404, json={"error": "coin not found"})
    elif provider == "twelvedata":
        response = httpx.Response(
            200,
            json={"code": 404, "status": "error", "message": "symbol not found"},
        )
    else:
        response = httpx.Response(
            200,
            text="Date,Open,High,Low,Close,Volume\nNo data,-,-,-,-,-\n",
        )
    route = _route(provider).mock(return_value=response)
    symbol = "ZZZZ" if provider != "coingecko" else "NOPEUSD"
    payload = await get_history(symbol, provider=provider, period="5d", **WHEN)
    error = _error(payload)
    assert error["code"] == expected
    if provider == "yahoo":
        assert "404" in str(error["message"])
    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_toml_only_key_is_redacted_in_the_tool_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CAPYBUCKS_TWELVEDATA_KEY", raising=False)
    config = tmp_path / "capybucks.toml"
    config.write_text(f'[keys]\ntwelvedata = "{TOML_KEY}"\n', encoding="utf-8")
    set_config_path(config)
    install_market()
    _route("twelvedata").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 400,
                "status": "error",
                "message": f"rejected credential {TOML_KEY}",
            },
        )
    )
    payload = await _history("twelvedata")
    error = _error(payload)
    assert error["code"] == "provider_error"
    assert TOML_KEY not in json.dumps(payload)
    assert "[redacted]" in str(error["message"])


@pytest.mark.asyncio
async def test_every_http_request_is_get(
    monkeypatch: pytest.MonkeyPatch, td_key: str
) -> None:
    install_market()
    methods: list[str] = []
    chart = json.loads(
        (FIXTURES / "yahoo" / "chart_aapl.json").read_text(encoding="utf-8")
    )
    btc = json.loads(
        (FIXTURES / "coingecko" / "btc_ohlc.json").read_text(encoding="utf-8")
    )
    series = json.loads(
        (FIXTURES / "twelvedata" / "time_series_aapl.json").read_text(encoding="utf-8")
    )
    stooq = (FIXTURES / "stooq" / "aapl.csv").read_text(encoding="utf-8")

    class RecordingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            methods.append(request.method)
            host = request.url.host
            if host == "api.coingecko.com":
                return httpx.Response(200, json=btc)
            if host == "api.twelvedata.com":
                return httpx.Response(200, json=series)
            if host == "stooq.com":
                return httpx.Response(200, text=stooq)
            if host == "query1.finance.yahoo.com":
                return httpx.Response(200, json=chart)
            return httpx.Response(599, text=f"unexpected host {host}")

    def client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=RecordingTransport())

    monkeypatch.setattr("capybucks.core.http._client", client)
    yahoo = await get_history("AAPL", provider="yahoo", period="5d", **WHEN)
    gecko = await get_history("BTC-USD", period="5d", **WHEN)
    stooq_payload = await get_history("AAPL", provider="stooq", period="5d", **WHEN)
    twelve = await get_history("AAPL", provider="twelvedata", period="5d", **WHEN)
    quote = await get_quote("AAPL", provider="yahoo")
    news = await get_news("AAPL", provider="yahoo")
    financials = await get_financials("AAPL", provider="yahoo")
    actions = await get_dividends_and_splits("AAPL", provider="yahoo")
    expirations = await get_option_expirations("AAPL", provider="yahoo")
    assert yahoo["ok"] is True
    assert gecko["ok"] is True
    assert stooq_payload["ok"] is True
    assert twelve["ok"] is True
    assert quote["ok"] is True
    assert methods
    assert set(methods) == {"GET"}
    assert len(methods) >= 5
    for payload in (news, financials, actions, expirations):
        blob = json.dumps(payload)
        assert "Traceback (most recent call last)" not in blob
        assert td_key not in blob
