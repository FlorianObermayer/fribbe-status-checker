import pytest

from app.services.occupancy.model import OccupancyType
from app.services.occupancy.occupancy_parser import (
    Weekday,
    _parse_event_calendar_row,  # pyright: ignore[reportPrivateUsage]
    _parse_weekly_plan_row,  # pyright: ignore[reportPrivateUsage]
    parse_weekly_plan,
)
from tests.test_utils import get_weekly_mock_table


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
        ("2026-05-01", "Turnier", "10:00 - 18:00", "komplett", OccupancyType.FULLY),
        ("2026-05-01", "Turnier", "10:00 - 18:00", "Komplett", OccupancyType.FULLY),
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
