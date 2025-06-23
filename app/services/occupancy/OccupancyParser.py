from datetime import datetime, timedelta
from typing import List
from bs4 import Tag

from app.services.occupancy.Occupancy import Occupancy
from app.services.occupancy.OccupancyType import OccupancyType

def verify_table_headers(table: Tag, *headers: str):
    actual_headers = [
        th.get_text(strip=True) for th in table.find("tr").find_all("th")
    ]
    if list(headers) != actual_headers:
        raise Exception(
            f"Table headers do not match expected.\nexpected: {list(headers)}\nactual: {actual_headers}"
        )

def parse_weekly_plan(weekly_plan_table: Tag) -> List[Occupancy]:
    occupancies: List[Occupancy] = []
    current_day = None
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
    day: str, time: str, event_name: str, location_field: str
) -> Occupancy:
    start_str, end_str = [t.strip() for t in time.split("-")]
    weekday_map = {
        "Montag": 0,
        "Dienstag": 1,
        "Mittwoch": 2,
        "Donnerstag": 3,
        "Freitag": 4,
        "Samstag": 5,
        "Sonntag": 6,
    }
    today = datetime.now().date()
    today_weekday = today.weekday()
    event_weekday = weekday_map.get(day, today_weekday)
    days_ahead = (event_weekday - today_weekday) % 7
    event_date = today + timedelta(days=days_ahead)
    match location_field:
        case "":
            occupancy_type = OccupancyType.NONE
        case _ if location_field.startswith("Feld"):
            occupancy_type = OccupancyType.PARTIALLY
        case _:
            occupancy_type = OccupancyType.FULLY

    try:
        start_time: datetime = datetime.strptime(
            f"{event_date} {start_str}", "%Y-%m-%d %H:%M"
        )
        end_time: datetime = datetime.strptime(
            f"{event_date} {end_str}", "%Y-%m-%d %H:%M"
        )
    except:
        start_time = datetime.strptime(f"{event_date} 00:00", "%Y-%m-%d %H:%M")
        end_time = datetime.strptime(f"{event_date} 23:59", "%Y-%m-%d %H:%M")

    return Occupancy(start_time, end_time, event_name, occupancy_type, location_field)


def parse_event_calendar(event_calendar_table: Tag) -> List[Occupancy]:
    return []
