from datetime import datetime, timedelta
from typing import List, Literal
from zoneinfo import ZoneInfo
from bs4 import Tag

from app.services.DatetimeParser import parse_event_times
from app.services.occupancy.Model import Occupancy
from app.services.occupancy.Model import OccupancySource
from app.services.occupancy.Model import OccupancyType

Weekday = Literal[
    "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"
]


def _verify_table_headers(table: Tag, *headers: str):
    actual_headers = [th.get_text(strip=True) for th in table.find("tr").find_all("th")]
    if list(headers) != actual_headers:
        raise Exception(
            f"Table headers do not match expected.\nexpected: {list(headers)}\nactual: {actual_headers}"
        )


def parse_weekly_plan(weekly_plan_table: Tag) -> List[Occupancy]:
    _verify_table_headers(weekly_plan_table, "Veranstaltung", "Zeit", "Ort / Felder")

    occupancies: List[Occupancy] = []
    current_day: Weekday | None = None
    for row in weekly_plan_table.find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue
        # Check for day row (colspan=3)
        if (
            len(cells) == 1
            and cells[0].has_attr("colspan")
            and cells[0]["colspan"] == "3"
        ):
            day_text = cells[0].get_text(strip=True)
            if day_text:
                current_day = day_text
            continue
        # Skip empty rows
        if all(cell.get_text(strip=True) == "" for cell in cells):
            continue
        # Normal event row
        if len(cells) == 3 and current_day and isinstance(current_day, str):
            event = str(cells[0].get_text(strip=True))
            time_str = str(cells[1].get_text(strip=True))
            location_field = str(cells[2].get_text(strip=True))
            if event == "" or location_field == "":
                continue
            occupancies.append(
                _parse_weekly_plan_data(current_day, time_str, event, location_field)
            )
    return occupancies


def _parse_weekly_plan_data(
    day: Weekday, time: str, event_name: str, location_field: str
) -> Occupancy:
    weekday_map: dict[Weekday, int] = {
        "Montag": 0,
        "Dienstag": 1,
        "Mittwoch": 2,
        "Donnerstag": 3,
        "Freitag": 4,
        "Samstag": 5,
        "Sonntag": 6,
    }
    today = datetime.now(tz=ZoneInfo("Europe/Berlin")).date()
    today_weekday = today.weekday()
    event_weekday = weekday_map.get(day, today_weekday)
    days_ahead = (event_weekday - today_weekday) % 7
    event_date = today + timedelta(days=days_ahead)
    match location_field:
        case "":
            occupancy_type = OccupancyType.NONE
        case _ if location_field.lower().startswith("feld"):
            occupancy_type = OccupancyType.PARTIALLY
        case _:
            occupancy_type = OccupancyType.FULLY

    start_time, end_time = parse_event_times(event_date, time)

    return Occupancy(
        start_time,
        end_time,
        event_name,
        occupancy_type,
        OccupancySource.WEEKLY_PLAN,
        location_field,
        time,
    )


def parse_event_calendar(event_calendar_table: Tag) -> List[Occupancy]:
    occupancies: List[Occupancy] = []
    _verify_table_headers(
        event_calendar_table, "Datum", "Veranstaltung", "Zeit", "Ort / Felder"
    )
    for row in event_calendar_table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) != 4:
            continue
        date_str = str(cells[0].get_text(strip=True))
        event_name = str(cells[1].get_text(strip=True))
        time_str = str(cells[2].get_text(strip=True))
        location_field = str(cells[3].get_text(strip=True))

        # Parse date
        data_date = row.get("data-date")
        if data_date and isinstance(data_date, str):
            event_date = data_date
        else:
            # fallback: try to parse from date_str (e.g. "01.05.")
            try:
                event_date = f"{datetime.now(tz=ZoneInfo('Europe/Berlin')).year}-{date_str[3:5]}-{date_str[0:2]}"
            except Exception:
                continue

        start_time, end_time = parse_event_times(event_date, time_str)

        # Occupancy type
        if not location_field or location_field == "-":
            occupancy_type = OccupancyType.NONE
        elif (
            location_field.lower().startswith("feld")
            or "feld" in location_field.lower()
        ):
            occupancy_type = OccupancyType.PARTIALLY
        elif location_field.lower().startswith("hütten"):
            occupancy_type = OccupancyType.PARTIALLY
        elif location_field.lower() == "komplett":
            occupancy_type = OccupancyType.FULLY
        else:
            occupancy_type = OccupancyType.PARTIALLY

        occupancies.append(
            Occupancy(
                start_time,
                end_time,
                event_name,
                occupancy_type,
                OccupancySource.EVENT_CALENDAR,
                location_field,
                time_str,
            )
        )
    return occupancies
