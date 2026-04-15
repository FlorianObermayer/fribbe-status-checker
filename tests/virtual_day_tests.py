from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.services.virtual_day import crossed_virtual_day, get_virtual_date

TZ = ZoneInfo("Europe/Berlin")


def test_get_virtual_date_before_5am() -> None:
    dt = datetime(2026, 4, 6, 4, 30, tzinfo=TZ)
    # 04:30 -> virtual date is previous day
    assert get_virtual_date(dt) == date(2026, 4, 5)


def test_get_virtual_date_exactly_5am() -> None:
    dt = datetime(2026, 4, 6, 5, 0, 0, tzinfo=TZ)
    assert get_virtual_date(dt) == date(2026, 4, 6)


def test_get_virtual_date_one_second_before_5am() -> None:
    dt = datetime(2026, 4, 6, 4, 59, 59, tzinfo=TZ)
    assert get_virtual_date(dt) == date(2026, 4, 5)


def test_get_virtual_date_after_5am() -> None:
    dt = datetime(2026, 4, 6, 6, 0, tzinfo=TZ)
    assert get_virtual_date(dt) == date(2026, 4, 6)


def test_crossed_virtual_day_true() -> None:
    prev = datetime(2026, 4, 5, 6, 0, tzinfo=TZ)
    now = datetime(2026, 4, 6, 6, 0, tzinfo=TZ)
    assert crossed_virtual_day(prev, now) is True


def test_crossed_virtual_day_false_same_virtual_date() -> None:
    prev = datetime(2026, 4, 6, 6, 0, tzinfo=TZ)
    now = datetime(2026, 4, 6, 23, 0, tzinfo=TZ)
    assert crossed_virtual_day(prev, now) is False


def test_crossed_virtual_day_true_at_boundary() -> None:
    prev = datetime(2026, 4, 6, 4, 59, 59, tzinfo=TZ)  # still virtual Apr 5
    now = datetime(2026, 4, 6, 5, 0, 0, tzinfo=TZ)  # now virtual Apr 6
    assert crossed_virtual_day(prev, now) is True


def test_crossed_virtual_day_none_prev() -> None:
    now = datetime(2026, 4, 6, 6, 0, tzinfo=TZ)
    assert crossed_virtual_day(None, now) is False
