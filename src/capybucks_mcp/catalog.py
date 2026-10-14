"""Static provider catalog.

``Registry._providers`` is private. This table is checked against the real
registry by ``tests/tools/test_providers.py``. If the library adds a provider,
that test fails until the table is updated.
"""

from __future__ import annotations

from dataclasses import dataclass

# Symbols capybucks.providers.coingecko.to_coingecko_id maps to a real id.
# Anything else is sent as symbol.lower(), which can be a different asset.
MAPPED_COINGECKO_SYMBOLS = frozenset(
    {
        "BTC",
        "BTC-USD",
        "BTCUSD",
        "ETH",
        "ETH-USD",
        "ETHUSD",
        "SOL",
        "SOL-USD",
    }
)


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    requires_key: bool
    default_for: tuple[str, ...]
    supports: dict[str, bool]
    delayed: bool
    notes: str

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "requires_key": self.requires_key,
            "default_for": list(self.default_for),
            "supports": dict(self.supports),
            "delayed": self.delayed,
            "notes": self.notes,
        }


_SUPPORTS = (
    "history",
    "quote",
    "statements",
    "options",
    "news",
    "actions",
    "stream",
)


def _supports(**flags: bool) -> dict[str, bool]:
    return {name: bool(flags.get(name, False)) for name in _SUPPORTS}


CATALOG: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        name="yahoo",
        requires_key=False,
        default_for=("equity",),
        supports=_supports(
            history=True,
            quote=True,
            statements=True,
            options=True,
            news=True,
            actions=True,
        ),
        delayed=True,
        notes=(
            "Default for equities. Unofficial Yahoo Finance endpoints "
            "(query1.finance.yahoo.com), usually delayed about 15 minutes. "
            "Terms restrict automated collection. Quote is the last daily bar."
        ),
    ),
    ProviderSpec(
        name="stooq",
        requires_key=False,
        default_for=(),
        supports=_supports(history=True),
        delayed=True,
        notes=(
            "History only. Pin with provider=stooq. Datacenter IPs often receive "
            "a bot-check page, which is a provider_error."
        ),
    ),
    ProviderSpec(
        name="coingecko",
        requires_key=False,
        default_for=("crypto",),
        supports=_supports(history=True, quote=True),
        delayed=True,
        notes=(
            "Default for crypto. Volume is not provided. Only BTC, ETH and SOL "
            "(and their -USD/USD forms) have a mapped id; other tickers are sent "
            "lowercased and can resolve to a different asset. "
            "Quote is the last daily bar."
        ),
    ),
    ProviderSpec(
        name="twelvedata",
        requires_key=True,
        default_for=(),
        supports=_supports(history=True, quote=True, statements=True, stream=True),
        delayed=True,
        notes=(
            "Official REST API. Requires CAPYBUCKS_TWELVEDATA_KEY. Needed for FX. "
            "The quote timestamp is the time of the call, not the trade. "
            "This server does not expose the stream."
        ),
    ),
)


def key_configured(provider: str) -> bool | None:
    """True when a key is configured. Never returns the key itself."""
    try:
        from capybucks.core.config import get_api_key
    except Exception:
        return None
    try:
        return bool(get_api_key(provider))
    except Exception:
        return None
