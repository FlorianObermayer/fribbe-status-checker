from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.occupancy.model import OccupancyType
from app.services.occupancy.occupancy_parser import (
    Weekday,
    _parse_event_calendar_row,  # pyright: ignore[reportPrivateUsage]
    _parse_weekly_plan_row,
    parse_event_calendar,  # pyright: ignore[reportPrivateUsage]
    parse_weekly_plan,
)
from tests.test_utils import get_calendar_mock_table, get_weekly_mock_table


@pytest.mark.parametrize(
    ("day", "time", "event_name", "location_field", "expected"),
    [
        (
            "Donnerstag",
            "18:00 - 19:00",
            "testing",
            "Feld 1, 2, 3 und 5",
            OccupancyType.PARTIALLY,
        ),
        ("Montag", "18:00 - 19:00", "testing", "Feld 1", OccupancyType.PARTIALLY),
        ("Montag", "18:00 - 19:00", "testing", "Feld 1,4", OccupancyType.PARTIALLY),
        ("Donnerstag", "18:00 - 19:00", "testing", "", OccupancyType.NONE),
        (
            "Mittwoch",
            "18:00 - 19:00",
            "testing",
            "Feld 3 und 5",
            OccupancyType.PARTIALLY,
        ),
        (
            "Freitag",
            "18:00 - 19:00",
            "testing",
            "irgendwas mit Medien",
            OccupancyType.FULLY,
        ),
        ("Dienstag", "13:30 - 16:00", "P-Seminar MT", "tbd", OccupancyType.PARTIALLY),
    ],
)
def test_parse_weekly_plan_data(
    day: Weekday,
    time: str,
    event_name: str,
    location_field: str,
    expected: OccupancyType,
) -> None:
    assert _parse_weekly_plan_row(day, time, event_name, location_field).occupancy_type == expected


def test_parse_table_returns_occupancies() -> None:
    table = get_weekly_mock_table()
    occupancies = parse_weekly_plan(table)
    assert len(occupancies) > 0
    assert any(o.event_name == "Hobbygruppe" for o in occupancies)
    assert any(o.occupied_str == "tbd" for o in occupancies)


def test_parse_table_skips_empty_events() -> None:
    table = get_weekly_mock_table()
    occupancies = parse_weekly_plan(table)
    assert not any(o.begin.weekday == 1 for o in occupancies)
    assert not any(o.end and o.end.weekday == 1 for o in occupancies)


@pytest.mark.parametrize(
    ("event_date", "event_name", "time_str", "location_field", "expected"),
    [
        ("2026-05-01", "Turnier", "10:00 - 18:00", "Feld 1, 2, 3", OccupancyType.PARTIALLY),
        ("2026-05-01", "Turnier", "10:00 - 18:00", "Feld 4", OccupancyType.PARTIALLY),
        ("2026-05-01", "Turnier", "10:00 - 18:00", "Hauptfeld", OccupancyType.PARTIALLY),
        ("2026-05-01", "Turnier", "10:00 - 18:00", "Sonderfeld Mitte", OccupancyType.PARTIALLY),
        ("2026-05-01", "Turnier", "10:00 - 18:00", "komplett", OccupancyType.PARTIALLY),
        ("2026-05-01", "Turnier", "10:00 - 20:00", "komplett", OccupancyType.FULLY),
        ("2026-05-01", "Turnier", "10:00 - 18:00", "Komplett", OccupancyType.PARTIALLY),
        ("2026-05-01", "Turnier", "10:00 - 18:00", "hütten", OccupancyType.PARTIALLY),
        ("2026-05-01", "Turnier", "10:00 - 18:00", "Hütten Nord", OccupancyType.PARTIALLY),
        ("2026-05-01", "Turnier", "10:00 - 18:00", "-", OccupancyType.NONE),
        ("2026-05-01", "Turnier", "10:00 - 18:00", "", OccupancyType.NONE),
    ],
)
def test_parse_event_calendar_row(
    event_date: str,
    event_name: str,
    time_str: str,
    location_field: str,
    expected: OccupancyType,
) -> None:
    result = _parse_event_calendar_row(event_date, event_name, time_str, location_field)
    assert result.occupancy_type == expected
    assert result.event_name == event_name


def test_parse_event_calendar_row_propagates_fields() -> None:
    result = _parse_event_calendar_row("2026-06-15", "Sommerfest", "14:00 - 20:00", "Feld 1")
    assert result.event_name == "Sommerfest"
    assert result.occupied_str == "Feld 1"
    assert result.time_str == "14:00 - 20:00"


# <tr data-day="dienstag"><td>Externe Buchung</td><td>18:00 - 20:00</td><td>Feld 4</td></tr>
def test_regression_parse_weekly_tuesday_external_booking_event() -> None:
    table = get_weekly_mock_table("data/snapshots/occupancy_weekly/2026_07_21.html")
    occupancies = parse_weekly_plan(table)
    assert any(o.event_name == "Externe Buchung" and o.begin.weekday() == 1 for o in occupancies)
    assert any(o.event_name == "Externe Buchung" and o.end and o.end.weekday() == 1 for o in occupancies)
    assert any(o.event_name == "Externe Buchung" and o.occupied_str == "Feld 4" for o in occupancies)
    assert any(o.event_name == "Externe Buchung" and o.occupancy_type == OccupancyType.PARTIALLY for o in occupancies)
    assert any(o.event_name == "Externe Buchung" and o.time_str == "18:00 - 20:00" for o in occupancies)


# <tr data-date="2026-07-21"><td>21.07.2026</td><td>Schulveranstaltung</td><td>bis 16 Uhr</td><td>komplett</td></tr>  <!-- Beachcamp MT -->
def test_regression_parse_calendar_should_be_partially_blocking_event() -> None:
    table = get_calendar_mock_table("data/snapshots/occupancy_calendar/2026_07_21.html")
    occupancies = parse_event_calendar(table)
    school_event = next(
        (o for o in occupancies if o.event_name == "Schulveranstaltung" and o.begin.date() == date(2026, 7, 21)), None
    )

    assert school_event is not None
    assert school_event.occupied_str == "komplett"
    assert school_event.occupancy_type == OccupancyType.PARTIALLY
    assert school_event.end is not None
    assert (
        school_event.end.time() == datetime.strptime("16:00", "%H:%M").replace(tzinfo=ZoneInfo("Europe/Berlin")).time()
    )
