import asyncio
from datetime import datetime, timedelta
from enum import Enum, Flag, auto
import logging
import threading
import time
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup, Tag
from dataclasses import dataclass
from typing import List, Tuple
import re

logger = logging.getLogger("uvicorn.error")


class Fields(Flag):
    NONE = auto()
    FIELD1 = auto()
    FIELD2 = auto()
    FIELD3 = auto()
    FIELD4 = auto()
    FIELD5 = auto()
    ALL_FIELDS = FIELD1 | FIELD2 | FIELD3 | FIELD4 | FIELD5


class OccupancyType(str, Enum):
    NONE = "none"
    PARTIALLY = "partially"
    FULLY = "fully"


@dataclass
class Occupancy:
    day: str
    time: str
    event: str
    location_field: str

    def __post_init__(self):
        start_str, end_str = [t.strip() for t in self.time.split("-")]
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
        event_weekday = weekday_map.get(self.day, today_weekday)
        days_ahead = (event_weekday - today_weekday) % 7
        event_date = today + timedelta(days=days_ahead)
        self.occupied_fields = self._parse_fields(self.location_field)

        try:
            self.start_time: datetime = datetime.strptime(
                f"{event_date} {start_str}", "%Y-%m-%d %H:%M"
            )
            self.end_time: datetime = datetime.strptime(
                f"{event_date} {end_str}", "%Y-%m-%d %H:%M"
            )
        except:
            self.start_time = datetime.strptime(f"{event_date} 00:00", "%Y-%m-%d %H:%M")
            self.end_time = datetime.strptime(f"{event_date} 23:59", "%Y-%m-%d %H:%M")

        self.fully_blocked = (
            self.end_time - self.start_time > timedelta(hours=8)
            and self.occupied_fields == Fields.ALL_FIELDS
        )

    def _parse_fields(self, location_field: str | Fields) -> Fields:
        if isinstance(location_field, Fields):
            return location_field

        if location_field == "":
            return Fields.NONE

        try:
            field_map = {
                "1": Fields.FIELD1,
                "2": Fields.FIELD2,
                "3": Fields.FIELD3,
                "4": Fields.FIELD4,
                "5": Fields.FIELD5,
            }
            # Collect all unique field numbers from both patterns
            numbers = re.findall(r"Feld\s*([1-5])", location_field)
            numbers += [
                num
                for num in re.findall(r"([1-5])", location_field)
                if num not in numbers
            ]
            parsed = Fields(0)
            for num in numbers:
                if num in field_map:
                    parsed |= field_map[num]
            if parsed == Fields(0):
                return (
                    Fields.ALL_FIELDS
                )  # default if message was something non-standard
            return parsed
        except:
            return Fields.NONE


class OccupancyService:
    def __init__(self, source_url: str):
        self.source_url = source_url
        self._week_occupancy: List[Occupancy]
        self._last_updated = datetime.now(tz=ZoneInfo("Europe/Berlin"))
        self._interval_thread = None
        self._stop_event = threading.Event()

    def get_todays_occupancy(self) -> Tuple[str, OccupancyType, datetime]:
        """
        Retrieves today's occupancy information.

        This method filters the week's occupancy data to find all occupancy entries for the current day
        (using the "Europe/Berlin" timezone). It then constructs a summary message listing all today's
        occupancies, their start and end times, event names, and locations. The overall occupancy type
        is set to `OccupancyType.FULLY` if any of today's occupancies are fully blocked; otherwise,
        it defaults to `OccupancyType.NONE`.

        Returns:
            Tuple[str, OccupancyType, datetime]:
                - A message summarizing today's occupancies, or a message indicating no occupancies.
                - The overall occupancy type for today.
                - The timestamp of the last update.
        """
        today = datetime.now(tz=ZoneInfo("Europe/Berlin")).date()
        todays_occupancies = [
            occ
            for occ in getattr(self, "_week_occupancy", [])
            if hasattr(occ, "start_time")
            and occ.start_time
            and occ.start_time.date() == today
        ]

        if not todays_occupancies:
            return (
                "Heute gibt es keine Feldbelegungen.",
                OccupancyType.NONE,
                self._last_updated,
            )

        lines: List[str] = []
        occupancy: OccupancyType = OccupancyType.NONE
        for occ in todays_occupancies:
            start = occ.start_time.strftime("%H:%M") if occ.start_time else occ.time
            end = occ.end_time.strftime("%H:%M") if occ.end_time else ""
            ort = occ.location_field

            lines.append(f"{start} - {end}: {occ.event} ({ort})")
            if getattr(occ, "fully_blocked", True):
                occupancy = OccupancyType.FULLY

        # TODO: also: figure out if each occupation potentially overlaps with other resulting in a fully blocked scenario

        message = "Belegung heute:\n" + "\n".join(lines)
        return (message, occupancy, self._last_updated)

    async def _get_occupancy_data(self) -> Tag:
        import urllib.request

        with urllib.request.urlopen(self.source_url) as response:
            if response.status != 200:
                raise Exception(f"Failed to fetch page: {response.status}")
            html = response.read().decode("utf-8")

        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        if len(tables) != 1:
            raise Exception("Expected exactly one table on the page.")

        table: Tag = tables[0]
        headers = [th.get_text(strip=True) for th in table.find("tr").find_all("th")]
        expected_headers = ["Tag", "Veranstaltung", "Zeit", "Ort / Felder"]
        if headers != expected_headers:
            raise Exception(f"Table headers do not match expected: {headers}")

        return table

    def _parse_table(self, html_table: Tag) -> List[Occupancy]:
        occupancies: List[Occupancy] = []
        current_day = None
        for row in html_table.find_all("tr"):
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
                event: str = cells[0].get_text(strip=True)
                time_str = cells[1].get_text(strip=True)
                location_field = cells[2].get_text(strip=True)
                if event == "" or location_field == "":
                    continue
                occupancies.append(
                    Occupancy(current_day, time_str, event, location_field)
                )
        return occupancies

    async def _run_get_latest_occupancy(self):
        try:
            logger.info(f"Refresh occupancy...")
            table = await self._get_occupancy_data()
            self._week_occupancy = self._parse_table(table)
            self._last_updated = datetime.now(tz=ZoneInfo("Europe/Berlin"))
            logger.info(f"Refresh occupancy... DONE")
        except Exception as e:
            logger.error(f"Error during occupancy check: {e}", exc_info=True)

    def _occupancy_loop(self, interval: int):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while not self._stop_event.is_set():
            loop.run_until_complete(self._run_get_latest_occupancy())
            time.sleep(interval)

    def start_status_check(self, interval: int = 360):
        if self._interval_thread is None or not self._interval_thread.is_alive():
            self._stop_event.clear()
            self._interval_thread = threading.Thread(
                target=self._occupancy_loop,
                args=[interval],
                daemon=True,
            )
            self._interval_thread.start()

    def stop_status_check(self):
        if self._interval_thread and self._interval_thread.is_alive():
            self._stop_event.set()
            self._interval_thread.join()
            self._interval_thread = None
