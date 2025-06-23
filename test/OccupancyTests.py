import pytest

from app.OccupancyService import Fields, Occupancy, OccupancyType


@pytest.mark.parametrize(
    "day,time,event_name,location_field,expected",
    [
        (
            "Donnerstag",
            "18:00 - 19:00",
            "testing",
            "Feld 1, 2, 3, 4 und 5",
            Fields.ALL_FIELDS,
        ),
        ("Montag", "18:00 - 19:00", "testing", "Feld 1", Fields.FIELD1),
        ("Montag", "18:00 - 19:00", "testing", "Feld 1,4", Fields.FIELD1|Fields.FIELD4),
        ("Donnerstag", "18:00 - 19:00", "testing", "", Fields.NONE),
        (
            "Mittwoch",
            "18:00 - 19:00",
            "testing",
            "Feld 3 und 5",
            Fields.FIELD3 | Fields.FIELD5,
        ),
        (
            "Freitag",
            "18:00 - 19:00",
            "testing",
            "irgendwas mit Medien",
            Fields.ALL_FIELDS,
        ),
    ],
)
def test_parsing_fields_data(
    day: str, time: str, event_name: str, location_field: str, expected: OccupancyType
):
    assert Occupancy(day, time, event_name, location_field).occupied_fields == expected
