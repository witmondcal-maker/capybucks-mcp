"""Live provider smoke. Excluded from the default pytest run."""

from __future__ import annotations

import os

import pytest
from tests.conftest import install_market

from capybucks_mcp.tools.history import get_history

pytestmark = pytest.mark.live


@pytest.mark.asyncio
async def test_yahoo_aapl_and_petr4_live() -> None:
    install_market()
    aapl = await get_history("AAPL", period="5d", provider="yahoo", use_cache=False)
    assert aapl["ok"] is True
    petr = await get_history("PETR4.SA", period="5d", provider="yahoo", use_cache=False)
    assert petr["ok"] is True
    provenance = petr["provenance"]
    assert isinstance(provenance, dict)
    assert provenance["currency"] == "BRL"
    assert provenance["timezone"] == "America/Sao_Paulo"


@pytest.mark.asyncio
async def test_coingecko_btc_live() -> None:
    install_market()
    payload = await get_history("BTC-USD", period="5d", use_cache=False)
    assert payload["ok"] is True
    provenance = payload["provenance"]
    assert isinstance(provenance, dict)
    assert provenance["provider"] == "coingecko"


@pytest.mark.asyncio
async def test_yahoo_unknown_symbol_is_provider_error_not_symbol_not_found() -> None:
    """Phase 0 finding: Yahoo HTTP 404 becomes ProviderError inside capybucks.

    The server must not invent a SymbolNotFound mapping. If the library starts
    raising SymbolNotFound for this case, this smoke test fails on purpose.
    """
    install_market()
    payload = await get_history(
        "NOTAREALTICKERXYZ", period="5d", provider="yahoo", use_cache=False
    )
    assert payload["ok"] is False
    error = payload["error"]
    assert isinstance(error, dict)
    assert error["code"] == "provider_error"
    assert "404" in str(error["message"])


@pytest.mark.asyncio
async def test_twelvedata_live() -> None:
    if not os.environ.get("CAPYBUCKS_TWELVEDATA_KEY"):
        pytest.skip("CAPYBUCKS_TWELVEDATA_KEY is not set")
    install_market()
    payload = await get_history(
        "AAPL", period="5d", provider="twelvedata", use_cache=False
    )
    assert payload["ok"] is True
