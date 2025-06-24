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
)
from app.services.occupancy.OccupancySource import OccupancySource
from app.services.occupancy.OccupancyType import OccupancyType


logger = logging.getLogger("uvicorn.error")


class OccupancyService:

    def __init__(self):
        self.weekly_plan_url = "https://fribbebeach.de/fribbe/belegungsplan.html"
        self.event_calendar_url = (
            "https://fribbebeach.de/fribbe/veranstaltungskalender.html"
        )
        self._week_occupancy: List[Occupancy] = []
        self._event_occupancy: List[Occupancy] = []
        self._last_updated = datetime.now(tz=ZoneInfo("Europe/Berlin"))
        self._interval_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_error: Exception | None = None

    def get_todays_occupancy(
        self,
    ) -> Tuple[
        List[str],
        List[Occupancy],
        OccupancyType,
        OccupancySource,
        datetime,
        Exception | None,
    ]:
        """
        Retrieves today's occupancy information.

        Returns:
            Tuple[List[str], OccupancyType, OccupancySource, datetime, Exception | None]:
                - A list of messages if today's occupancies or an empty list.
                - The overall occupancy type for today.
                - The source of the occupancy (event calendar or weekly plan)
                - The timestamp of the last update.
                - the last parsing error if there was any
        """
        today = datetime.now(tz=ZoneInfo("Europe/Berlin")).date()
        todays_occupancies = [
            occ
            for occ in self._week_occupancy + self._event_occupancy
            if occ.begin.date() == today
        ]

        if not todays_occupancies:
            return (
                [],
                [],
                OccupancyType.NONE,
                OccupancySource.WEEKLY_PLAN,
                self._last_updated,
                self._last_error,
            )

        lines: List[str] = []
        occupancy: OccupancyType = OccupancyType.PARTIALLY
        source: OccupancySource = OccupancySource.WEEKLY_PLAN

        events: List[Occupancy] = []
        for occ in sorted(todays_occupancies, key=lambda o: o.begin):
            location = occ.occupied_str

            events.append(occ)
            lines.append(f"{occ.time_str}: {occ.event_name} ({location})")

            if occ.occupancy_type == OccupancyType.FULLY:
                occupancy = OccupancyType.FULLY

            if occ.occupancy_source == OccupancySource.EVENT_CALENDAR:
                source = OccupancySource.EVENT_CALENDAR

        # TODO: Also figure out if each occupation potentially overlaps with other resulting in a fully blocked scenario

        return (lines, events, occupancy, source, self._last_updated, self._last_error)

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

        return tables[0]  # type: ignore

    async def _run_get_latest_occupancy(self):
        try:
            logger.info(f"Refresh occupancy...")
            weekly_table = await OccupancyService._get_occupancy_data(
                self.weekly_plan_url
            )
            self._week_occupancy = parse_weekly_plan(weekly_table)

            event_table = await OccupancyService._get_occupancy_data(
                self.event_calendar_url
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

    def start_polling(self, interval: int = 360):
        if self._interval_thread is None or not self._interval_thread.is_alive():
            self._stop_event.clear()
            self._interval_thread = threading.Thread(
                target=self._occupancy_loop,
                args=[interval],
                daemon=True,
            )
            self._interval_thread.start()

    def stop_polling(self):
        if self._interval_thread and self._interval_thread.is_alive():
            self._stop_event.set()
            self._interval_thread.join()
            self._interval_thread = None
