import pytest

from app import env
from app.format import seconds_to_human


def test_zero_seconds() -> None:
    assert seconds_to_human(0) == "0 Sekunden"


def test_one_second() -> None:
    assert seconds_to_human(1) == "1 Sekunde"


def test_seconds_only() -> None:
    assert seconds_to_human(45) == "45 Sekunden"


def test_one_minute() -> None:
    assert seconds_to_human(60) == "1 Minute"


def test_minutes_and_seconds() -> None:
    assert seconds_to_human(90) == "1 Minute, 30 Sekunden"


def test_one_hour() -> None:
    assert seconds_to_human(3600) == "1 Stunde"


def test_hours_and_minutes() -> None:
    assert seconds_to_human(3660) == "1 Stunde, 1 Minute"


def test_one_day() -> None:
    assert seconds_to_human(86400) == "1 Tag"


def test_seven_days() -> None:
    assert seconds_to_human(604800) == "7 Tage"


def test_complex_duration() -> None:
    assert seconds_to_human(90061) == "1 Tag, 1 Stunde, 1 Minute, 1 Sekunde"


def test_default_session_max_age() -> None:
    assert seconds_to_human(env.SESSION_MAX_AGE_SECONDS) == "7 Tage"


def test_negative_raises() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        seconds_to_human(-1)
