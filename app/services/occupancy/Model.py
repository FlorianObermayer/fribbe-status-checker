from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class OccupancyType(StrEnum):
    NONE = "none"
    PARTIALLY = "partially"
    FULLY = "fully"


class OccupancySource(StrEnum):
    WEEKLY_PLAN = "weekly_plan"
    EVENT_CALENDAR = "event_calendar"


@dataclass
class Occupancy:
    begin: datetime
    end: datetime | None
    event_name: str
    occupancy_type: OccupancyType
    occupancy_source: OccupancySource
    occupied_str: str
    time_str: str
