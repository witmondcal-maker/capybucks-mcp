"""Isolated capybucks state for every test."""

from __future__ import annotations

from pathlib import Path

import pytest
from capybucks.async_api.download import configure_cache
from capybucks.core.bootstrap import install_default_providers
from capybucks.core.config import set_config_path
from capybucks.core.models import AssetType
from capybucks.core.registry import get_registry, reset_registry
from capybucks.providers.memory import MemoryProvider

from capybucks_mcp.guard import reset_guard
from capybucks_mcp.ttl_cache import reset_ttl_cache


def install_market() -> None:
    """Register the real default providers. Tests that need them call this."""
    reset_registry()
    install_default_providers(get_registry())


@pytest.fixture(autouse=True)
def isolated_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    monkeypatch.setenv("CAPYBUCKS_NO_RATELIMIT", "1")
    if request.node.get_closest_marker("live") is None:
        monkeypatch.delenv("CAPYBUCKS_TWELVEDATA_KEY", raising=False)
    set_config_path(tmp_path / "capybucks.toml")
    reset_registry()
    get_registry().register(
        MemoryProvider(),
        default_for=((AssetType.EQUITY, "*"),),
    )
    configure_cache(tmp_path / "cache")
    reset_guard()
    reset_ttl_cache()
    yield
    reset_registry()
    set_config_path(None)
    reset_guard()
    reset_ttl_cache()
