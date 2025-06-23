import asyncio
from datetime import datetime
import logging
import threading
import time
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup, Tag
from typing import List, Tuple

from app.services.occupancy.Occupancy import Occupancy
from app.services.occupancy.OccupancyParser import (
    parse_event_calendar,
    parse_weekly_plan,
    verify_table_headers,
)
from app.services.occupancy.OccupancyType import OccupancyType


logger = logging.getLogger("uvicorn.error")


class OccupancyService:
    def __init__(self, weekly_plan_url: str, event_calendar_url: str):
        self.weekly_plan_url = weekly_plan_url
        self.event_calendar_url = event_calendar_url
        self._week_occupancy: List[Occupancy] = []
        self._event_occupancy: List[Occupancy] = []
        self._last_updated = datetime.now(tz=ZoneInfo("Europe/Berlin"))
        self._interval_thread : threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_error: Exception | None = None

    def get_todays_occupancy(
        self,
    ) -> Tuple[str, OccupancyType, datetime, Exception | None]:
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
                self._last_error,
            )

        lines: List[str] = []
        occupancy: OccupancyType = OccupancyType.PARTIALLY
        for occ in todays_occupancies:
            start = occ.start_time.strftime("%H:%M") if occ.start_time else occ.time
            end = occ.end_time.strftime("%H:%M") if occ.end_time else ""
            ort = occ.location_field

            lines.append(f"{start} - {end}: {occ.event} ({ort})")
            if getattr(occ, "fully_blocked", True):
                occupancy = OccupancyType.FULLY

        # TODO: Also figure out if each occupation potentially overlaps with other resulting in a fully blocked scenario

        message = "Belegung heute:\n" + "\n".join(lines)
        return (message, occupancy, self._last_updated, self._last_error)

    @staticmethod
    async def _get_occupancy_data(source_url: str) -> Tag:
        import urllib.request

        with urllib.request.urlopen(source_url) as response:
            if response.status != 200:
                raise Exception(f"Failed to fetch page: {response.status}")
            html = response.read().decode("utf-8")

        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        if len(tables) != 1:
            raise Exception("Expected exactly one table on the page.")

        table: Tag = tables[0]

        return table

    async def _run_get_latest_occupancy(self):
        try:
            logger.info(f"Refresh occupancy...")
            weekly_table = await OccupancyService._get_occupancy_data(
                self.weekly_plan_url
            )
            verify_table_headers(weekly_table, "Veranstaltung", "Zeit", "Ort / Felder")
            self._week_occupancy = parse_weekly_plan(weekly_table)

            event_table = await OccupancyService._get_occupancy_data(
                self.event_calendar_url
            )
            verify_table_headers(
                event_table, "Datum", "Veranstaltung", "Zeit", "Ort / Felder"
            )

            self._event_occupancy = parse_event_calendar(event_table)
            self._last_updated = datetime.now(tz=ZoneInfo("Europe/Berlin"))
            self._last_error = None
            logger.info(f"Refresh occupancy... DONE")
        except Exception as e:
            self._last_error = e
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
