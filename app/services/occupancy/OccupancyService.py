import asyncio
from datetime import date, datetime, timedelta
import logging
import threading
import time
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup, Tag
from typing import List, Tuple

import dateparser

from app.services.occupancy.Occupancy import Occupancy
from app.services.occupancy.OccupancyParser import (
    parse_event_calendar,
    parse_weekly_plan,
)
from app.services.occupancy.OccupancySource import OccupancySource
from app.services.occupancy.OccupancyType import OccupancyType
from dataclasses import replace


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

    def get_occupancy(self, for_date_str: str) -> Tuple[
        date,
        List[str],
        List[Occupancy],
        OccupancyType,
        OccupancySource,
        datetime,
        Exception | None,
    ]:
        """
        Retrieves occupancy information for a given date.

        Args:
            for_date_str (str): The date string (in any parseable format) for which to retrieve occupancy information.

            Tuple[
                date,              # The parsed date object, today's date if parsing failed.
                List[str],         # Human-readable lines describing each occupancy event for the date.
                List[Occupancy],   # List of Occupancy objects for the date.
                OccupancyType,     # The overall occupancy type for the date (e.g., PARTIALLY, FULLY, NONE).
                OccupancySource,   # The source of the occupancy information (e.g., WEEKLY_PLAN, EVENT_CALENDAR).
                datetime,          # The timestamp of the last update to the occupancy data.
                Exception | None   # The last parsing error encountered, or None if there was no error.

        Notes:
            - If no occupancies are found for the given date, returns empty lists and OccupancyType.NONE.
            - The occupancy type is set to FULLY if any event for the date is fully occupied.
            - The source is set to EVENT_CALENDAR if any event for the date comes from the event calendar.
            - The method does not currently check for overlapping events that might result in a fully blocked scenario.
        """
        for_date = (
            dateparser.parse(
                for_date_str,
                languages=["de", "en"],
                settings={"TIMEZONE": "Europe/Berlin"},
            )
            or datetime.now()
        ).date()
        filtered_occupancies = [
            occ
            for occ in self._week_occupancy + self._event_occupancy
            if occ.begin.date() == for_date
        ]

        if not filtered_occupancies:
            return (
                for_date,
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
        for occ in sorted(filtered_occupancies, key=lambda o: o.begin):
            location = occ.occupied_str
            message = f"{occ.time_str}: {occ.event_name} ({location})"

            events.append(occ)
            lines.append(message)

            if occ.occupancy_type == OccupancyType.FULLY:
                occupancy = OccupancyType.FULLY

            if occ.occupancy_source == OccupancySource.EVENT_CALENDAR:
                source = OccupancySource.EVENT_CALENDAR

            # a full day blocking event should overrule everything
            if (
                occ.occupancy_type == OccupancyType.FULLY
                and occ.occupancy_source == OccupancySource.EVENT_CALENDAR
            ):
                lines = [message]
                events = [occ]
                break

        # TODO: Also figure out if each occupation potentially overlaps with other resulting in a fully blocked scenario

        return (
            for_date,
            lines,
            events,
            occupancy,
            source,
            self._last_updated,
            self._last_error,
        )

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

    def _extend_to(self, events: List[Occupancy], count: int) -> List[Occupancy]:
        if len(events) >= count:
            return events
        if len(events) < 7:
            raise Exception("Illegal number of events for _extend_to")

        weeks = int(count / 7)
        sorted_events = sorted(events, key=lambda o: o.begin)
        result: List[Occupancy] = [*sorted_events]
        for i in range(1, weeks):
            for event in sorted_events:
                shifted_occ = replace(
                    event,
                    begin=event.begin + timedelta(days=7 * i),
                    end=(
                        event.end + timedelta(days=7 * i)
                        if event.end is not None
                        else None
                    ),
                )
                result.append(shifted_occ)
        return result

    async def _run_get_latest_occupancy(self):
        try:
            logger.info(f"Refresh occupancy...")
            weekly_table = await OccupancyService._get_occupancy_data(
                self.weekly_plan_url
            )
            self._week_occupancy = self._extend_to(parse_weekly_plan(weekly_table), 365)

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
