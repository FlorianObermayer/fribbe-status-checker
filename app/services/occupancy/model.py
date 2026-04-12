from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class OccupancyType(StrEnum):
    """How much of the venue is occupied."""

    NONE = "none"
    PARTIALLY = "partially"
    FULLY = "fully"


class OccupancySource(StrEnum):
    """Origin of the occupancy data."""

    WEEKLY_PLAN = "weekly_plan"
    EVENT_CALENDAR = "event_calendar"


@dataclass
class Occupancy:
    """A single scheduled event with its occupancy impact."""

    begin: datetime
    end: datetime | None
    event_name: str
    occupancy_type: OccupancyType
    occupancy_source: OccupancySource
    occupied_str: str
    time_str: str


@dataclass
class DailyOccupancy:
    """Aggregated occupancy information for one day."""

    date: date
    lines: list[str]
    events: list[Occupancy]
    occupancy_type: OccupancyType
    occupancy_source: OccupancySource
    last_updated: datetime
    error: Exception | None

    """Container for occupancy information.

    Fields:
        date: Parsed target date.
        lines: Human-readable lines describing events for the date.
        events: List of `Occupancy` objects for the date.
        occupancy_type: Overall occupancy classification for the date.
        occupancy_source: Source of the occupancy data.
        last_updated: Timestamp when occupancy data was last refreshed.
        error: The last exception encountered while fetching/parsing data, if any.
    """
