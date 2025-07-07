import pytest
from datetime import date, datetime
from app.services.DatetimeParser import parse_event_times

@pytest.mark.parametrize(
    "date_input, time_str, expected",
    [
        # date as date object, time as "HH:MM-HH:MM"
        (
            date(2024, 6, 10),
            "09:00-10:30",
            (
                datetime(2024, 6, 10, 9, 0),
                datetime(2024, 6, 10, 10, 30),
            ),
        ),
        # date as string, time as "HH:MM-HH:MM"
        (
            "2024-06-11",
            "14:15-16:00",
            (
                datetime(2024, 6, 11, 14, 15),
                datetime(2024, 6, 11, 16, 0),
            ),
        ),
        # midnight event
        (
            date(2024, 6, 12),
            "00:00-01:00",
            (
                datetime(2024, 6, 12, 0, 0),
                datetime(2024, 6, 12, 1, 0),
            ),
        ),
        # event ending at midnight
        (
            "2024-06-13",
            "22:30-00:00",
            (
                datetime(2024, 6, 13, 22, 30),
                datetime(2024, 6, 14, 0, 0),
            ),
        ),
        # event spanning over midnight
        (
            date(2024, 6, 14),
            "23:00-01:00",
            (
                datetime(2024, 6, 14, 23, 0),
                datetime(2024, 6, 15, 1, 0),
            ),
        ),
        # event with single digit hour
        (
            "2024-06-15",
            "8:00-9:45",
            (
                datetime(2024, 6, 15, 8, 0),
                datetime(2024, 6, 15, 9, 45),
            ),
        ),
        # event with no minutes
        (
            date(2024, 6, 16),
            "10:00-12:00",
            (
                datetime(2024, 6, 16, 10, 0),
                datetime(2024, 6, 16, 12, 0),
            ),
        ),
        # event with start time after end time (should go to next day)
        (
            "2024-06-17",
            "23:30-01:15",
            (
                datetime(2024, 6, 17, 23, 30),
                datetime(2024, 6, 18, 1, 15),
            ),
        ),
        # ganztags
        (
            date(2024, 6, 16),
            "ganztags",
            (
                datetime(2024, 6, 16, 0, 0),
                datetime(2024, 6, 16, 23, 59),
            ),
        ),
        # ganztägig
        (
            "2024-06-17",
            "ganztägig",
            (
                datetime(2024, 6, 17, 0, 0),
                datetime(2024, 6, 17, 23, 59),
            ),
        ),
        # vormittags
        (
            date(2024, 6, 18),
            "vormittags",
            (
                datetime(2024, 6, 18, 8, 0),
                datetime(2024, 6, 18, 12, 0),
            ),
        ),
        # abends
        (
            "2024-06-19",
            "abends",
            (
                datetime(2024, 6, 19, 18, 0),
                datetime(2024, 6, 19, 22, 0),
            ),
        ),
        # nachmittags
        (
            date(2024, 6, 20),
            "nachmittags",
            (
                datetime(2024, 6, 20, 15, 0),
                datetime(2024, 6, 20, 18, 0),
            ),
        ),
        # ab mittag
        (
            "2024-06-21",
            "ab mittag",
            (
                datetime(2024, 6, 21, 12, 0),
                datetime(2024, 6, 21, 18, 0),
            ),
        ),
        # mit ?? als Endzeit
        (
            date(2024, 6, 22),
            "13:00 - ?? Uhr",
            (
                datetime(2024, 6, 22, 13, 0),
                datetime(2024, 6, 22, 23, 59),
            ),
        ),
        # nur Bindestrich
        (
            "2024-06-23",
            "-",
            (
                datetime(2024, 6, 23, 0, 0),
                datetime(2024, 6, 23, 23, 59),
            ),
        ),
        # leere Zeit
        (
            date(2024, 6, 24),
            "",
            (
                datetime(2024, 6, 24, 0, 0),
                datetime(2024, 6, 24, 23, 59),
            ),
        ),
        # nur Startzeit, default 2h Dauer
        (
            "2024-06-25",
            "10:00 Uhr",
            (
                datetime(2024, 6, 25, 10, 0),
                datetime(2024, 6, 25, 12, 0),
            ),
        ),
        # wilde Eingabe, sollte fallback auf all-day
        (
            date(2024, 6, 26),
            "irgendwas komisches",
            (
                datetime(2024, 6, 26, 0, 0),
                datetime(2024, 6, 26, 23, 59),
            ),
        ),
         # natürliche Sprache
        (
            date(2024, 6, 26),
            "übermorgen",
            (
                datetime(2024, 6, 28, 0, 0),
                datetime(2024, 6, 28, 2, 0),
            ),
        ),
         # natürliche Sprache
        (
            date(2024, 6, 26),
            "übermorgen um 17:00 Uhr",
            (
                datetime(2024, 6, 28, 17, 0),
                datetime(2024, 6, 28, 19, 0),
            ),
        ),
    ]
)
def test_parameterized(date_input: str | date, time_str:str, expected:tuple[datetime,datetime]):
    actual = parse_event_times(date_input, time_str)
    assert actual == expected