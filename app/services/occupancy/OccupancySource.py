from enum import Enum


class OccupancySource(str, Enum):
    WEEKLY_PLAN = "weekly_plan"
    EVENT_CALENDAR = "event_calendar"
