from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx
from capybucks.core.models import AssetType, History
from capybucks.core.provider import Provider
from capybucks.core.registry import get_registry, reset_registry
from capybucks.exceptions import ProviderError
from tests.conftest import install_market

from capybucks_mcp.catalog import CATALOG
from capybucks_mcp.config import ALLOWED_HOSTS
from capybucks_mcp.tools.calendar import check_trading_day
from capybucks_mcp.tools.fundamentals import get_dividends_and_splits, get_financials
from capybucks_mcp.tools.history import get_history, get_quote
from capybucks_mcp.tools.indicators import compute_indicators
from capybucks_mcp.tools.news import get_news
from capybucks_mcp.tools.options import get_option_chain, get_option_expirations
from capybucks_mcp.tools.providers import list_providers

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
START = datetime(2024, 1, 1, tzinfo=UTC)
END = datetime(2024, 1, 10, tzinfo=UTC)


def _error(payload: dict[str, object]) -> dict[str, object]:
    error = payload["error"]
    assert isinstance(error, dict)
    return error


def test_list_providers_hides_keys_and_warns_about_yahoo() -> None:
    import asyncio

    payload = asyncio.run(list_providers())
    assert payload["ok"] is True
    assert "provenance" not in payload
    warnings = payload["warnings"]
    assert isinstance(warnings, list)
    assert any("not an official API" in item for item in warnings)
    data = payload["data"]
    assert isinstance(data, dict)
    providers = data["providers"]
    assert isinstance(providers, list)
    assert [row["name"] for row in providers if isinstance(row, dict)] == [
        spec.name for spec in CATALOG
    ]
    blob = json.dumps(payload)
    for row in providers:
        assert isinstance(row, dict)
        assert isinstance(row["key_configured"], bool)
    assert "sk-" not in blob


def test_list_providers_matches_registry() -> None:
    from capybucks.core.provider import Provider as BaseProvider

    install_market()
    registry = get_registry()
    names = set(registry._providers)
    assert names == {spec.name for spec in CATALOG}
    methods = {
        "history": "fetch_history",
        "quote": "fetch_quote",
        "statements": "fetch_statement",
        "options": "fetch_option_chain",
        "news": "fetch_news",
        "actions": "fetch_actions",
    }
    for spec in CATALOG:
        provider = registry.get(spec.name)
        assert provider.requires_key is spec.requires_key
        assert provider.supports_stream is spec.supports["stream"]
        for capability, method in methods.items():
            implemented = getattr(type(provider), method) is not getattr(
                BaseProvider, method
            )
            assert implemented is spec.supports[capability]


@pytest.mark.asyncio
async def test_history_memory_has_provenance() -> None:
    payload = await get_history(
        "AAPL", period="5d", start="2024-01-01", end="2024-01-05"
    )
    assert payload["ok"] is True
    provenance = payload["provenance"]
    assert isinstance(provenance, dict)
    assert provenance["provider"] == "memory"
    assert provenance["currency"] == "USD"
    assert isinstance(provenance["asof"], str)
    data = payload["data"]
    assert isinstance(data, dict)
    assert data["symbol"] == "AAPL"
    rows = data["rows"]
    assert isinstance(rows, list)
    assert rows[0]["open"] == 100.0
    assert "sk-" not in json.dumps(payload)


@pytest.mark.asyncio
async def test_unknown_symbol_and_hyphen_and_batch() -> None:
    missing = await get_history("NOPE")
    assert _error(missing)["code"] == "symbol_not_found"
    hyphen = await get_history("BRK-B")
    assert _error(hyphen)["code"] == "no_provider"
    warnings = hyphen["warnings"]
    assert isinstance(warnings, list)
    assert any("BRK-B" in item for item in warnings)
    mixed = await get_history(["AAPL", "NOPE"], start="2024-01-01", end="2024-01-05")
    assert mixed["ok"] is True
    data = mixed["data"]
    assert isinstance(data, dict)
    series = data["series"]
    errors = data["errors"]
    assert isinstance(series, dict) and "AAPL" in series
    assert isinstance(errors, dict) and "NOPE" in errors
    failed = await get_history(["NOPE", "ZZZZ"])
    assert _error(failed)["code"] == "all_symbols_failed"


@pytest.mark.asyncio
async def test_invalid_symbol_and_summary() -> None:
    bad = await get_history("AAPL;rm")
    assert _error(bad)["code"] == "invalid_argument"
    summary = await get_history(
        "AAPL",
        view="summary",
        start="2024-01-01T00:00:00+00:00",
        end="2024-01-10T00:00:00+00:00",
    )
    assert summary["ok"] is True
    data = summary["data"]
    assert isinstance(data, dict)
    block = data["summary"]
    assert isinstance(block, dict)
    assert block["first_close"] == 100.0
    assert isinstance(block["change_pct"], float)
    warnings = summary["warnings"]
    assert isinstance(warnings, list)
    assert any("computed by the server" in item for item in warnings)


@pytest.mark.asyncio
async def test_quote_memory() -> None:
    payload = await get_quote("AAPL")
    assert payload["ok"] is True
    data = payload["data"]
    assert isinstance(data, dict)
    assert data["price"] == 100.0
    assert data["quote_kind"] == "provider_quote"
    assert data["delayed"] is False
    warnings = payload["warnings"]
    assert isinstance(warnings, list)
    assert any("last daily bar" in item for item in warnings)


@pytest.mark.asyncio
async def test_financials_dividends_options_news_indicators_calendar() -> None:
    financials = await get_financials("AAPL", statement="income", frequency="annual")
    assert financials["ok"] is True
    data = financials["data"]
    assert isinstance(data, dict)
    items = data["items"]
    assert isinstance(items, dict)
    assert "Total Revenue" in items

    actions = await get_dividends_and_splits("AAPL")
    assert actions["ok"] is True
    action_data = actions["data"]
    assert isinstance(action_data, dict)
    dividends = action_data["dividends"]
    splits = action_data["splits"]
    assert isinstance(dividends, list) and dividends[0]["amount"] == 0.24
    assert isinstance(splits, list) and splits[0]["ratio"] == 4.0

    empty = await get_dividends_and_splits("AAPL", since="2024-01-01T00:00:00+00:00")
    assert empty["ok"] is True
    empty_data = empty["data"]
    assert isinstance(empty_data, dict)
    assert empty_data["dividends"] == []
    assert empty_data["splits"] == []

    expirations = await get_option_expirations("AAPL")
    assert expirations["ok"] is True
    exp_data = expirations["data"]
    assert isinstance(exp_data, dict)
    assert exp_data["expirations"][0] == "2024-01-19"

    chain = await get_option_chain("AAPL", expiration="2024-01-19", near_money=True)
    assert chain["ok"] is True
    chain_data = chain["data"]
    assert isinstance(chain_data, dict)
    calls = chain_data["calls"]
    assert isinstance(calls, list)
    assert calls[0]["contract_symbol"].startswith("AAPL")
    assert "strike" in calls[0]

    news = await get_news("AAPL")
    assert news["ok"] is True
    news_data = news["data"]
    assert isinstance(news_data, dict)
    assert news_data["untrusted_text"] is True
    headlines = news_data["items"]
    assert isinstance(headlines, list)
    assert headlines[0]["title"] == "AAPL test headline"

    indicators = await compute_indicators(
        "AAPL", indicators=["sma"], window=2, period="1mo", last_n=5
    )
    assert indicators["ok"] is True
    ind_data = indicators["data"]
    assert isinstance(ind_data, dict)
    columns = ind_data["columns"]
    assert isinstance(columns, list)
    assert "sma" in columns
    rows = ind_data["rows"]
    assert isinstance(rows, list)
    assert any(
        row[columns.index("sma")] is not None for row in rows if isinstance(row, list)
    )

    saturday = await check_trading_day("AAPL", date="2024-01-06")
    assert saturday["ok"] is True
    sat_data = saturday["data"]
    assert isinstance(sat_data, dict)
    assert sat_data["calendar"] == "XNYS"
    assert sat_data["is_session"] is False
    tuesday = await check_trading_day("AAPL", date="2024-01-02")
    tue_data = tuesday["data"]
    assert isinstance(tue_data, dict)
    assert tue_data["is_session"] is True
    b3 = await check_trading_day("PETR4.SA", date="2024-01-06")
    b3_data = b3["data"]
    assert isinstance(b3_data, dict)
    assert b3_data["calendar"] == "BVMF"
    assert b3_data["is_session"] is False


@pytest.mark.asyncio
async def test_unsupported_statement_and_fx() -> None:
    install_market()
    payload = await get_financials("AAPL", provider="coingecko")
    assert _error(payload)["code"] == "unsupported_capability"
    fx = await get_history("EUR/USD")
    assert _error(fx)["code"] == "no_provider"


class _LeakProvider(Provider):
    name = "yahoo"
    requires_key = False

    def supports(self, asset_type: AssetType) -> bool:
        return asset_type is AssetType.EQUITY

    async def fetch_history(
        self,
        symbol: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
        auto_adjust: bool = True,
    ) -> History:
        raise ProviderError(
            "GET https://api.twelvedata.com/quote?apikey=sk-test-123&symbol=AAPL failed"
        )


@pytest.mark.asyncio
async def test_tool_response_scrubs_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAPYBUCKS_TWELVEDATA_KEY", "sk-test-123")
    reset_registry()
    get_registry().register(_LeakProvider(), default_for=((AssetType.EQUITY, "*"),))
    payload = await get_history("AAPL", provider="yahoo")
    blob = json.dumps(payload)
    assert "sk-test-123" not in blob
    assert "apikey=[redacted]" in blob
    assert _error(payload)["code"] == "provider_error"


def _forbid(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"unexpected host {request.url.host}")


@respx.mock
@pytest.mark.asyncio
async def test_recorded_fixtures_and_hosts() -> None:
    install_market()
    petr = json.loads(
        (FIXTURES / "yahoo" / "chart_petr4.json").read_text(encoding="utf-8")
    )
    btc = json.loads(
        (FIXTURES / "coingecko" / "btc_ohlc.json").read_text(encoding="utf-8")
    )
    td = json.loads(
        (FIXTURES / "twelvedata" / "time_series_aapl.json").read_text(encoding="utf-8")
    )
    stooq = (FIXTURES / "stooq" / "aapl.csv").read_text(encoding="utf-8")
    respx.get(
        url__regex=r"https://query1\.finance\.yahoo\.com/v8/finance/chart/PETR4\.SA.*"
    ).mock(return_value=httpx.Response(200, json=petr))
    respx.get(
        url__regex=r"https://api\.coingecko\.com/api/v3/coins/bitcoin/ohlc.*"
    ).mock(return_value=httpx.Response(200, json=btc))
    respx.get(url__regex=r"https://api\.twelvedata\.com/time_series.*").mock(
        return_value=httpx.Response(200, json=td)
    )
    respx.get(url__regex=r"https://stooq\.com/q/d/l/.*").mock(
        return_value=httpx.Response(200, text=stooq)
    )
    respx.route(url__regex=r"https?://.*").mock(side_effect=_forbid)

    import os

    os.environ["CAPYBUCKS_TWELVEDATA_KEY"] = "fixture-key-not-real"
    try:
        petr_payload = await get_history(
            "PETR4.SA",
            provider="yahoo",
            start="2024-01-01T00:00:00+00:00",
            end="2024-01-10T00:00:00+00:00",
            use_cache=False,
        )
        btc_payload = await get_history(
            "BTC-USD",
            start="2024-01-01T00:00:00+00:00",
            end="2024-01-10T00:00:00+00:00",
            use_cache=False,
        )
        td_payload = await get_history(
            "AAPL",
            provider="twelvedata",
            start="2024-01-01T00:00:00+00:00",
            end="2024-01-10T00:00:00+00:00",
            use_cache=False,
        )
        stooq_payload = await get_history(
            "AAPL",
            provider="stooq",
            start="2024-01-01T00:00:00+00:00",
            end="2024-01-10T00:00:00+00:00",
            use_cache=False,
        )
    finally:
        os.environ.pop("CAPYBUCKS_TWELVEDATA_KEY", None)

    assert petr_payload["ok"] is True
    petr_prov = petr_payload["provenance"]
    assert isinstance(petr_prov, dict)
    assert petr_prov["currency"] == "BRL"
    assert petr_prov["timezone"] == "America/Sao_Paulo"
    warnings = petr_payload["warnings"]
    assert isinstance(warnings, list)
    assert any("not an official API" in item for item in warnings)

    assert btc_payload["ok"] is True
    btc_data = btc_payload["data"]
    assert isinstance(btc_data, dict)
    btc_rows = btc_data["rows"]
    assert isinstance(btc_rows, list)
    assert all(row["volume"] is None for row in btc_rows if isinstance(row, dict))
    btc_warnings = btc_payload["warnings"]
    assert isinstance(btc_warnings, list)
    assert any("volume not provided" in item for item in btc_warnings)

    assert td_payload["ok"] is True
    assert "fixture-key-not-real" not in json.dumps(td_payload)
    assert stooq_payload["ok"] is True
    for call in respx.calls:
        assert call.request.url.host in ALLOWED_HOSTS
