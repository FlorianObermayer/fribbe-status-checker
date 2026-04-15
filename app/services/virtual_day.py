from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app import env

DEFAULT_RESET_HOUR = 5


def get_virtual_date(dt: datetime, reset_hour: int = DEFAULT_RESET_HOUR) -> date:
    """Return the "virtual" date for a datetime using the given reset hour.

    The virtual date is defined as (dt - reset_hour hours).date().
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(env.TZ))
    return (dt - timedelta(hours=reset_hour)).date()


def crossed_virtual_day(prev_dt: datetime | None, now_dt: datetime, reset_hour: int = DEFAULT_RESET_HOUR) -> bool:
    """Return True if virtual date changed between prev_dt and now_dt.

    If prev_dt is None, return False.
    """
    if prev_dt is None:
        return False
    return get_virtual_date(prev_dt, reset_hour) < get_virtual_date(now_dt, reset_hour)
