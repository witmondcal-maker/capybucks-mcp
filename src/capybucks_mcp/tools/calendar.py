"""``check_trading_day``."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from capybucks.calendars import calendar_for_symbol, get_calendar, is_session

from capybucks_mcp.envelope import success
from capybucks_mcp.errors import failure_envelope
from capybucks_mcp.validate import parse_date, parse_symbol

_OPEN_WARNING = (
    "This only says whether the date is an exchange session. "
    "It does not say whether the market is open right now."
)


async def check_trading_day(
    symbol: str,
    date: str | None = None,
    calendar: str | None = None,
) -> dict[str, object]:
    try:
        parsed = parse_symbol(symbol)
        code = calendar or calendar_for_symbol(parsed)
        try:
            exchange = get_calendar(code)
        except Exception as exc:
            raise ValueError(f"unknown calendar {code!r}") from exc
        if date is None:
            zone = ZoneInfo(str(exchange.tz))
            today = datetime.now(zone).date()
            when = datetime(today.year, today.month, today.day)
            day = today.isoformat()
        else:
            when = parse_date(date)
            day = date
        session = bool(is_session(when, symbol=parsed, calendar=code))
        return success(
            tool="check_trading_day",
            data={
                "symbol": parsed,
                "calendar": code,
                "date": day,
                "is_session": session,
            },
            warnings=[_OPEN_WARNING],
        )
    except Exception as exc:
        return failure_envelope("check_trading_day", exc)
