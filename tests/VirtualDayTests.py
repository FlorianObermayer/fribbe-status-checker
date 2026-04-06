from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.services.VirtualDay import crossed_virtual_day, get_virtual_date

TZ = ZoneInfo("Europe/Berlin")


def test_get_virtual_date_before_5am():
    dt = datetime(2026, 4, 6, 4, 30, tzinfo=TZ)
    # 04:30 -> virtual date is previous day
    assert get_virtual_date(dt) == date(2026, 4, 5)


def test_get_virtual_date_after_5am():
    dt = datetime(2026, 4, 6, 6, 0, tzinfo=TZ)
    assert get_virtual_date(dt) == date(2026, 4, 6)


def test_crossed_virtual_day_true():
    prev = datetime(2026, 4, 5, 6, 0, tzinfo=TZ)
    now = datetime(2026, 4, 6, 6, 0, tzinfo=TZ)
    assert crossed_virtual_day(prev, now) is True


def test_crossed_virtual_day_none_prev():
    now = datetime(2026, 4, 6, 6, 0, tzinfo=TZ)
    assert crossed_virtual_day(None, now) is False
