"""Percent-encode symbols at the provider path templates."""

from __future__ import annotations

from types import ModuleType
from urllib.parse import quote


class _QuotedPath:
    def __init__(self, template: str) -> None:
        self._template = template

    def format(self, **kwargs: str) -> str:
        encoded = {key: quote(value, safe="") for key, value in kwargs.items()}
        return self._template.format(**encoded)


def _wrap(module: ModuleType, name: str) -> None:
    current: object = getattr(module, name)
    if isinstance(current, _QuotedPath) or not isinstance(current, str):
        return
    setattr(module, name, _QuotedPath(current))


def install_quoted_path_templates() -> None:
    import capybucks.providers.coingecko as coingecko
    import capybucks.providers.yahoo as yahoo
    import capybucks.providers.yahoo_fundamentals as fundamentals

    _wrap(yahoo, "_CHART")
    _wrap(fundamentals, "_SUMMARY")
    _wrap(fundamentals, "_OPTIONS")
    _wrap(fundamentals, "_CHART")
    _wrap(coingecko, "_OHLC")
