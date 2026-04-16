import logging
import urllib.request
from dataclasses import replace
from datetime import datetime, timedelta
from http import HTTPStatus
from zoneinfo import ZoneInfo

import dateparser
from bs4 import BeautifulSoup, Tag
from readerwriterlock import rwlock

from app.config import cfg
from app.services.occupancy.model import DailyOccupancy, Occupancy, OccupancySource, OccupancyType
from app.services.occupancy.occupancy_parser import (
    parse_event_calendar,
    parse_weekly_plan,
)
from app.services.polling_service import PollingService

logger = logging.getLogger("uvicorn.error")

_MIN_WEEKLY_EVENTS = 7


class OccupancyService(PollingService):
    """Poll fribbebeach.de for weekly and event occupancy data."""

    def __init__(self) -> None:
        super().__init__()
        self.weekly_plan_url = "https://fribbebeach.de/fribbe/belegungsplan.html"
        self.event_calendar_url = "https://fribbebeach.de/fribbe/veranstaltungskalender.html"
        self._week_occupancy: list[Occupancy] = []
        self._event_occupancy: list[Occupancy] = []
        self._last_updated = datetime.now(tz=ZoneInfo(cfg.TZ))
        self._last_error: Exception | None = None
        self._rwlock = rwlock.RWLockFair()

    def get_occupancy(self, for_date_str: str = "today") -> DailyOccupancy:
        """Retrieve occupancy information for a given date.

        Args:
            for_date_str (str): The date string (in any parseable format) for which to retrieve occupancy information.

            Returns: DailyOccupancy

        Notes:
            - If no occupancies are found for the given date, returns empty lists and OccupancyType.NONE.
            - The occupancy type is set to FULLY if any event for the date is fully occupied.
            - The source is set to EVENT_CALENDAR if any event for the date comes from the event calendar.
            - The method does not currently check for overlapping events that might result in a fully blocked scenario.

        """
        with self._rwlock.gen_rlock():
            for_date = (
                dateparser.parse(
                    for_date_str,
                    languages=["de", "en"],
                    settings={"TIMEZONE": cfg.TZ},
                )
                or datetime.now(tz=ZoneInfo(cfg.TZ))
            ).date()
            filtered_occupancies = [
                occ for occ in self._week_occupancy + self._event_occupancy if occ.begin.date() == for_date
            ]

            if not filtered_occupancies:
                return DailyOccupancy(
                    date=for_date,
                    lines=[],
                    events=[],
                    occupancy_type=OccupancyType.NONE,
                    occupancy_source=OccupancySource.WEEKLY_PLAN,
                    last_updated=self._last_updated,
                    error=self._last_error,
                )

            lines: list[str] = []
            occupancy: OccupancyType = OccupancyType.PARTIALLY
            source: OccupancySource = OccupancySource.WEEKLY_PLAN

            events: list[Occupancy] = []
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
                if occ.occupancy_type == OccupancyType.FULLY and occ.occupancy_source == OccupancySource.EVENT_CALENDAR:
                    lines = [message]
                    events = [occ]
                    break

            # TODO(FlorianObermayer): Also figure out if each occupation potentially overlaps  # noqa: FIX002
            # with other resulting in a fully blocked scenario
            # https://github.com/FlorianObermayer/fribbe-status-checker/issues/1

            return DailyOccupancy(
                date=for_date,
                lines=lines,
                events=events,
                occupancy_type=occupancy,
                occupancy_source=source,
                last_updated=self._last_updated,
                error=self._last_error,
            )

    @staticmethod
    def _get_occupancy_data(source_url: str) -> Tag:

        if not source_url.startswith(("http://", "https://")):
            msg = "URL must start with 'http://' or 'https://'"
            raise ValueError(msg)

        with urllib.request.urlopen(source_url) as response:  # noqa: S310
            if response.status != HTTPStatus.OK:
                msg = f"Failed to fetch page: {response.status}"
                raise RuntimeError(msg)
            html = response.read().decode("utf-8")

        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        if len(tables) != 1:
            msg = "Expected exactly one table on the page."
            raise ValueError(msg)

        return tables[0]

    def _extend_to(self, events: list[Occupancy], count: int) -> list[Occupancy]:
        if len(events) >= count:
            return events
        if len(events) < _MIN_WEEKLY_EVENTS:
            msg = "Illegal number of events for _extend_to"
            raise ValueError(msg)

        weeks = int(count / 7)
        sorted_events = sorted(events, key=lambda o: o.begin)
        result: list[Occupancy] = [*sorted_events]
        for i in range(1, weeks):
            for event in sorted_events:
                shifted_occ = replace(
                    event,
                    begin=event.begin + timedelta(days=7 * i),
                    end=(event.end + timedelta(days=7 * i) if event.end is not None else None),
                )
                result.append(shifted_occ)
        return result

    async def _run_poll(self) -> None:
        await self._run_get_latest_occupancy()

    async def _run_get_latest_occupancy(self) -> None:
        try:
            logger.info("Refresh occupancy...")
            weekly_table = OccupancyService._get_occupancy_data(self.weekly_plan_url)
            event_table = OccupancyService._get_occupancy_data(self.event_calendar_url)
            with self._rwlock.gen_wlock():
                self._week_occupancy = self._extend_to(parse_weekly_plan(weekly_table), 365)
                self._event_occupancy = parse_event_calendar(event_table)
                self._last_updated = datetime.now(tz=ZoneInfo(cfg.TZ))
                self._last_error = None
            logger.info("Refresh occupancy... DONE")
        except Exception as e:
            with self._rwlock.gen_wlock():
                self._last_error = e
            logger.exception("Error during occupancy check")

    def start_polling(self, interval: int = 360) -> None:  # type: ignore[override]
        """Begin periodic occupancy fetching."""
        super().start_polling(interval)
