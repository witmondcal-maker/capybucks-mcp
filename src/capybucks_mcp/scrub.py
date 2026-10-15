"""Remove API keys and ``CAPYBUCKS_*`` secret values from text leaving the process."""

from __future__ import annotations

import os
import re
import sys
import tomllib
from typing import TextIO, cast

from capybucks.core.config import config_path

_APIKEY = re.compile(r"(?i)(apikey|api_key|api-key)(=|%3D)[^&\s\"']+")
_MIN_SECRET_LEN = 6


def _remember(found: list[str], value: str) -> None:
    stripped = value.strip()
    if len(stripped) < _MIN_SECRET_LEN or stripped in found:
        return
    found.append(stripped)


def _toml_secrets() -> list[str]:
    path = config_path()
    if not path.is_file():
        return []
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    keys = raw.get("keys")
    if not isinstance(keys, dict):
        return []
    found: list[str] = []
    for value in keys.values():
        if isinstance(value, str):
            _remember(found, value)
    return found


def secret_values() -> list[str]:
    """Values that must never appear in a response or log line.

    Environment ``CAPYBUCKS_*_KEY`` values, other ``CAPYBUCKS_*`` values of
    at least 8 characters, and every key loaded from the capybucks toml.
    Short flags such as ``CAPYBUCKS_NO_RATELIMIT=1`` are left alone.
    """
    found: list[str] = []
    for key, value in os.environ.items():
        if not key.startswith("CAPYBUCKS_"):
            continue
        stripped = value.strip()
        if len(stripped) < _MIN_SECRET_LEN:
            continue
        if key.endswith("_KEY") or len(stripped) >= 8:
            _remember(found, stripped)
    for value in _toml_secrets():
        _remember(found, value)
    found.sort(key=len, reverse=True)
    return found


def scrub(text: str) -> str:
    """Redact query-string API keys and known secret values."""
    cleaned = _APIKEY.sub(r"\1\2[redacted]", text)
    for value in secret_values():
        if value in cleaned:
            cleaned = cleaned.replace(value, "[redacted]")
    return cleaned


class ScrubStream:
    """Text stream that scrubs every write before it reaches the underlying file."""

    def __init__(self, underlying: TextIO) -> None:
        self._underlying = underlying

    def write(self, data: str) -> int:
        return self._underlying.write(scrub(data))

    def flush(self) -> None:
        self._underlying.flush()

    def isatty(self) -> bool:
        isatty = getattr(self._underlying, "isatty", None)
        if callable(isatty):
            return bool(isatty())
        return False

    def __getattr__(self, name: str) -> object:
        return getattr(self._underlying, name)


def install_stderr_scrubber() -> None:
    """Wrap ``sys.stderr`` so tracebacks cannot print a Twelve Data key."""
    current = sys.stderr
    if isinstance(current, ScrubStream):
        return
    sys.stderr = cast(TextIO, ScrubStream(current))
