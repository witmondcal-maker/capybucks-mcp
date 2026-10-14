"""Map capybucks and transport exceptions onto the error envelope."""

from __future__ import annotations

import logging
import uuid
from typing import cast

import httpx
from capybucks.exceptions import (
    CapybucksError,
    MissingAPIKey,
    MultiDownloadError,
    NoProviderError,
    ProviderError,
    ProviderNotFound,
    RateLimitError,
    StreamingNotSupportedError,
    SymbolNotFound,
)

from capybucks_mcp.envelope import YAHOO_WARNING, failure
from capybucks_mcp.guard import CooldownActive
from capybucks_mcp.scrub import scrub

logger = logging.getLogger("capybucks_mcp")

_VALID_PROVIDERS = ["yahoo", "coingecko", "stooq", "twelvedata"]


class CallContextError(Exception):
    """An exception tagged with the provider and capability that was in use."""

    def __init__(
        self,
        cause: BaseException,
        *,
        provider: str | None,
        capability: str | None = None,
    ) -> None:
        super().__init__(scrub(str(cause)))
        self.cause = cause
        self.provider = provider
        self.capability = capability


def unwrap(exc: BaseException) -> tuple[BaseException, str | None, str | None]:
    provider: str | None = None
    capability: str | None = None
    current = exc
    while isinstance(current, CallContextError):
        provider = current.provider or provider
        capability = current.capability or capability
        current = current.cause
    return current, provider, capability


def _provider_of(exc: BaseException, fallback: str | None) -> str | None:
    value = getattr(exc, "provider", None)
    if isinstance(value, str) and value:
        return value
    return fallback


def _clean(text: str) -> str:
    return scrub(text)


def describe_error(
    exc: BaseException,
    *,
    provider: str | None = None,
    capability: str | None = None,
) -> dict[str, object]:
    """Return the inner ``error`` object for one exception."""
    inner, ctx_provider, ctx_capability = unwrap(exc)
    provider = _provider_of(inner, provider or ctx_provider)
    capability = capability or ctx_capability

    if isinstance(inner, CooldownActive):
        return {
            "code": "rate_limited",
            "type": "RateLimitError",
            "message": _clean(str(inner)),
            "retryable": True,
            "details": {
                "provider": inner.provider,
                "retry_after_seconds": inner.retry_after_seconds,
            },
            "next_step": (
                "Wait and retry this provider. Do not switch providers on your own. "
                "Yahoo may answer 403 as a bot wall; "
                "the library maps 403 to this error."
            ),
        }

    if isinstance(inner, SymbolNotFound):
        details: dict[str, object] = {
            "symbol": inner.symbol,
            "provider": inner.provider,
            "hint": inner.hint,
        }
        if inner.hint:
            next_step = f"Tell the user, then retry with symbol={inner.hint}."
        else:
            next_step = "Ask the user for another symbol. Do not guess a rewrite."
        return {
            "code": "symbol_not_found",
            "type": "SymbolNotFound",
            "message": _clean(str(inner)),
            "retryable": False,
            "details": details,
            "next_step": next_step,
        }

    if isinstance(inner, MissingAPIKey):
        env_var = f"CAPYBUCKS_{inner.provider.upper()}_KEY"
        return {
            "code": "missing_api_key",
            "type": "MissingAPIKey",
            "message": _clean(str(inner)),
            "retryable": False,
            "details": {"provider": inner.provider, "env_var": env_var},
            "next_step": (
                f"Configure {env_var} in the plugin variables or ~/.capybucks.toml. "
                "Never ask the user to paste the key in chat."
            ),
        }

    if isinstance(inner, RateLimitError):
        retry_after = getattr(inner, "retry_after_seconds", None)
        if not isinstance(retry_after, int):
            from capybucks_mcp.config import load_config

            retry_after = int(load_config().cooldown_seconds)
        return {
            "code": "rate_limited",
            "type": "RateLimitError",
            "message": _clean(str(inner)),
            "retryable": True,
            "details": {"provider": provider, "retry_after_seconds": retry_after},
            "next_step": (
                "Wait and retry this provider. Do not switch providers on your own. "
                "Yahoo may answer 403 as a bot wall; "
                "the library maps 403 to this error."
            ),
        }

    if isinstance(inner, ProviderNotFound):
        return {
            "code": "unknown_provider",
            "type": "ProviderNotFound",
            "message": _clean(str(inner)),
            "retryable": False,
            "details": {"name": inner.name, "providers": list(_VALID_PROVIDERS)},
            "next_step": "Use a name from the list.",
        }

    if isinstance(inner, NoProviderError):
        return {
            "code": "no_provider",
            "type": "NoProviderError",
            "message": _clean(str(inner)),
            "retryable": False,
            "details": {
                "asset_type": inner.asset_type,
                "interval": inner.interval,
            },
            "next_step": (
                "For FX, pass provider=twelvedata and configure "
                "CAPYBUCKS_TWELVEDATA_KEY. Do not invent a fallback provider."
            ),
        }

    if isinstance(inner, MultiDownloadError):
        mapped: dict[str, object] = {}
        for symbol, item in inner.errors.items():
            mapped[symbol] = describe_error(
                item, provider=provider, capability=capability
            )
        return {
            "code": "all_symbols_failed",
            "type": "MultiDownloadError",
            "message": _clean(str(inner)),
            "retryable": False,
            "details": {"errors": mapped},
            "next_step": (
                "Inspect each symbol error. Do not switch providers on your own."
            ),
        }

    if isinstance(inner, StreamingNotSupportedError):
        return {
            "code": "streaming_unsupported",
            "type": "StreamingNotSupportedError",
            "message": _clean(str(inner)),
            "retryable": False,
            "details": {"provider": inner.provider},
            "next_step": (
                "This server has no streaming tool. Use get_quote or get_history."
            ),
        }

    if isinstance(inner, ProviderError):
        text = str(inner).lower()
        retryable = "http 5" in text or "bot-check" in text or "timeout" in text
        # HTTP 404 stays provider_error. core/http.py raises before Yahoo's
        # chart parser can turn the body into SymbolNotFound. Do not remap.
        return {
            "code": "provider_error",
            "type": "ProviderError",
            "message": _clean(str(inner)),
            "retryable": retryable,
            "details": {"provider": provider, "message": _clean(str(inner))},
            "next_step": (
                "Read the message. Interval and bot-check failures need a different "
                "argument or a later retry of the same provider. Do not switch "
                "providers on your own."
            ),
        }

    if isinstance(inner, NotImplementedError):
        return {
            "code": "unsupported_capability",
            "type": "NotImplementedError",
            "message": _clean(str(inner)),
            "retryable": False,
            "details": {"provider": provider, "capability": capability},
            "next_step": (
                "This provider does not implement the dataset. "
                "Pass another provider explicitly, or accept the gap."
            ),
        }

    if isinstance(inner, ValueError):
        return {
            "code": "invalid_argument",
            "type": "ValueError",
            "message": _clean(str(inner)),
            "retryable": False,
            "details": {"message": _clean(str(inner))},
            "next_step": "Fix the argument and retry.",
        }

    if isinstance(inner, ImportError):
        extra = "calendars" if "calendar" in str(inner).lower() else "unknown"
        return {
            "code": "missing_extra",
            "type": "ImportError",
            "message": _clean(str(inner)),
            "retryable": False,
            "details": {"extra": extra},
            "next_step": (
                "Reinstall capybucks-mcp. The calendars extra is already a dependency."
            ),
        }

    if isinstance(inner, TimeoutError | httpx.HTTPError):
        return {
            "code": "network_error",
            "type": type(inner).__name__,
            "message": _clean(str(inner)) or "network error",
            "retryable": True,
            "details": {"provider": provider},
            "next_step": "Retry later. Do not switch providers on your own.",
        }

    if isinstance(inner, CapybucksError):
        return {
            "code": "provider_error",
            "type": type(inner).__name__,
            "message": _clean(str(inner)),
            "retryable": False,
            "details": {"provider": provider, "message": _clean(str(inner))},
            "next_step": "Read the message and retry only if the cause is transient.",
        }

    correlation_id = uuid.uuid4().hex[:12]
    logger.error("internal error %s", correlation_id, exc_info=inner)
    return {
        "code": "internal_error",
        "type": "InternalError",
        "message": "internal error",
        "retryable": False,
        "details": {"correlation_id": correlation_id},
        "next_step": "Retry later. If it persists, report the correlation id.",
    }


def failure_envelope(
    tool: str,
    exc: BaseException,
    *,
    extra_warnings: list[str] | None = None,
) -> dict[str, object]:
    _inner, provider, _capability = unwrap(exc)
    error = describe_error(exc)
    warnings = list(extra_warnings or [])
    if provider == "yahoo":
        warnings.append(YAHOO_WARNING)
    return failure(tool=tool, error=error, warnings=warnings)


def anticipated(exc: BaseException) -> bool:
    inner, _, _ = unwrap(exc)
    return isinstance(
        inner,
        CapybucksError
        | ValueError
        | NotImplementedError
        | ImportError
        | httpx.HTTPError
        | TimeoutError
        | CooldownActive,
    )


def as_error_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return {"message": _clean(str(value))}
