"""Remove API keys and ``CAPYBUCKS_*`` secret values from text leaving the process."""

from __future__ import annotations

import os
import re
import sys
from typing import TextIO, cast

_APIKEY = re.compile(r"(?i)(apikey|api_key|api-key)(=|%3D)[^&\s\"']+")
_MIN_SECRET_LEN = 6


def secret_values() -> list[str]:
    """Values that must never appear in a response or log line.

    Only ``CAPYBUCKS_*_KEY`` values, and other ``CAPYBUCKS_*`` values of at
    least 8 characters, are treated as secrets. Short flags such as
    ``CAPYBUCKS_NO_RATELIMIT=1`` are left alone.
    """
    found: list[str] = []
    for key, value in os.environ.items():
        if not key.startswith("CAPYBUCKS_"):
            continue
        stripped = value.strip()
        if len(stripped) < _MIN_SECRET_LEN:
            continue
        if key.endswith("_KEY") or len(stripped) >= 8:
            found.append(stripped)
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
