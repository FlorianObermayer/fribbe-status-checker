from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.datetime_parser import parse_event_times

_TZ = ZoneInfo("Europe/Berlin")


@pytest.mark.parametrize(
    ("date_input", "time_str", "expected"),
    [
        # date as date object, time as "HH:MM-HH:MM"
        (
            date(2024, 6, 10),
            "09:00-10:30",
            (
                datetime(2024, 6, 10, 9, 0, tzinfo=_TZ),
                datetime(2024, 6, 10, 10, 30, tzinfo=_TZ),
            ),
        ),
        # date as string, time as "HH:MM-HH:MM"
        (
            "2024-06-11",
            "14:15-16:00",
            (
                datetime(2024, 6, 11, 14, 15, tzinfo=_TZ),
                datetime(2024, 6, 11, 16, 0, tzinfo=_TZ),
            ),
        ),
        # midnight event
        (
            date(2024, 6, 12),
            "00:00-01:00",
            (
                datetime(2024, 6, 12, 0, 0, tzinfo=_TZ),
                datetime(2024, 6, 12, 1, 0, tzinfo=_TZ),
            ),
        ),
        # event ending at midnight
        (
            "2024-06-13",
            "22:30-00:00",
            (
                datetime(2024, 6, 13, 22, 30, tzinfo=_TZ),
                datetime(2024, 6, 14, 0, 0, tzinfo=_TZ),
            ),
        ),
        # event spanning over midnight
        (
            date(2024, 6, 14),
            "23:00-01:00",
            (
                datetime(2024, 6, 14, 23, 0, tzinfo=_TZ),
                datetime(2024, 6, 15, 1, 0, tzinfo=_TZ),
            ),
        ),
        # event with single digit hour
        (
            "2024-06-15",
            "8:00-9:45",
            (
                datetime(2024, 6, 15, 8, 0, tzinfo=_TZ),
                datetime(2024, 6, 15, 9, 45, tzinfo=_TZ),
            ),
        ),
        # event with no minutes
        (
            date(2024, 6, 16),
            "10:00-12:00",
            (
                datetime(2024, 6, 16, 10, 0, tzinfo=_TZ),
                datetime(2024, 6, 16, 12, 0, tzinfo=_TZ),
            ),
        ),
        # event with start time after end time (should go to next day)
        (
            "2024-06-17",
            "23:30-01:15",
            (
                datetime(2024, 6, 17, 23, 30, tzinfo=_TZ),
                datetime(2024, 6, 18, 1, 15, tzinfo=_TZ),
            ),
        ),
        # ganztags
        (
            date(2024, 6, 16),
            "ganztags",
            (
                datetime(2024, 6, 16, 0, 0, tzinfo=_TZ),
                datetime(2024, 6, 16, 23, 59, tzinfo=_TZ),
            ),
        ),
        # ganztägig
        (
            "2024-06-17",
            "ganztägig",
            (
                datetime(2024, 6, 17, 0, 0, tzinfo=_TZ),
                datetime(2024, 6, 17, 23, 59, tzinfo=_TZ),
            ),
        ),
        # vormittags
        (
            date(2024, 6, 18),
            "vormittags",
            (
                datetime(2024, 6, 18, 8, 0, tzinfo=_TZ),
                datetime(2024, 6, 18, 12, 0, tzinfo=_TZ),
            ),
        ),
        # abends
        (
            "2024-06-19",
            "abends",
            (
                datetime(2024, 6, 19, 18, 0, tzinfo=_TZ),
                datetime(2024, 6, 19, 22, 0, tzinfo=_TZ),
            ),
        ),
        # nachmittags
        (
            date(2024, 6, 20),
            "nachmittags",
            (
                datetime(2024, 6, 20, 15, 0, tzinfo=_TZ),
                datetime(2024, 6, 20, 18, 0, tzinfo=_TZ),
            ),
        ),
        # ab mittag
        (
            "2024-06-21",
            "ab mittag",
            (
                datetime(2024, 6, 21, 12, 0, tzinfo=_TZ),
                datetime(2024, 6, 21, 18, 0, tzinfo=_TZ),
            ),
        ),
        # mit ?? als Endzeit
        (
            date(2024, 6, 22),
            "13:00 - ?? Uhr",
            (
                datetime(2024, 6, 22, 13, 0, tzinfo=_TZ),
                datetime(2024, 6, 22, 23, 59, tzinfo=_TZ),
            ),
        ),
        # nur Bindestrich
        (
            "2024-06-23",
            "-",
            (
                datetime(2024, 6, 23, 0, 0, tzinfo=_TZ),
                datetime(2024, 6, 23, 23, 59, tzinfo=_TZ),
            ),
        ),
        # leere Zeit
        (
            date(2024, 6, 24),
            "",
            (
                datetime(2024, 6, 24, 0, 0, tzinfo=_TZ),
                datetime(2024, 6, 24, 23, 59, tzinfo=_TZ),
            ),
        ),
        # nur Startzeit, default 2h Dauer
        (
            "2024-06-25",
            "10:00 Uhr",
            (
                datetime(2024, 6, 25, 10, 0, tzinfo=_TZ),
                datetime(2024, 6, 25, 12, 0, tzinfo=_TZ),
            ),
        ),
        # wilde Eingabe, sollte fallback auf all-day
        (
            date(2024, 6, 26),
            "irgendwas komisches",
            (
                datetime(2024, 6, 26, 0, 0, tzinfo=_TZ),
                datetime(2024, 6, 26, 23, 59, tzinfo=_TZ),
            ),
        ),
        # natürliche Sprache
        (
            date(2024, 6, 26),
            "übermorgen",
            (
                datetime(2024, 6, 28, 0, 0, tzinfo=_TZ),
                datetime(2024, 6, 28, 2, 0, tzinfo=_TZ),
            ),
        ),
        # natürliche Sprache
        (
            date(2024, 6, 26),
            "übermorgen um 17:00 Uhr",
            (
                datetime(2024, 6, 28, 17, 0, tzinfo=_TZ),
                datetime(2024, 6, 28, 19, 0, tzinfo=_TZ),
            ),
        ),
    ],
)
def test_parameterized(date_input: str | date, time_str: str, expected: tuple[datetime, datetime]) -> None:
    actual = parse_event_times(date_input, time_str)
    assert actual == expected
