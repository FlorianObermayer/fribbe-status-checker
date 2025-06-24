import pytest

from app.services.occupancy.OccupancyParser import _parse_weekly_plan_data, parse_weekly_plan  # type: ignore
from app.services.occupancy.OccupancyType import OccupancyType
from test.test_utils import get_weekly_mock_table


@pytest.mark.parametrize(
    "day,time,event_name,location_field,expected",
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
    ],
)
def test_parse_weekly_plan_data(
    day: str, time: str, event_name: str, location_field: str, expected: OccupancyType
):
    assert _parse_weekly_plan_data(day, time, event_name, location_field).occupancy_type == expected


def test_parse_table_returns_occupancies():
    table = get_weekly_mock_table()
    occupancies = parse_weekly_plan(table)  # type: ignore
    assert len(occupancies) > 0
    assert any(o.event_name == "Hobbygruppe" for o in occupancies)


def test_parse_table_skips_empty_events():
    table = get_weekly_mock_table()
    occupancies = parse_weekly_plan(table)
    assert not any(o.begin.weekday == 1 for o in occupancies)
    assert not any(o.end and o.end.weekday == 1 for o in occupancies)
