from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.services.occupancy.Model import OccupancySource, OccupancyType
from app.services.occupancy.OccupancyParser import (
    parse_event_calendar,
    parse_weekly_plan,
)
from app.services.occupancy.OccupancyService import OccupancyService
from tests.test_utils import get_calendar_mock_table, get_weekly_mock_table


def service():
    return OccupancyService()


@pytest.mark.asyncio
@patch("app.services.occupancy.OccupancyService.OccupancyService._get_occupancy_data")
async def test_run_get_latest_occupancy_sets_week_occupancy(
    mock_get_occupancy_data: MagicMock,
):
    s = service()
    mock_get_occupancy_data.return_value = get_weekly_mock_table()
    await s._run_get_latest_occupancy()  # type: ignore
    assert hasattr(s, "_week_occupancy")
    assert len(s._week_occupancy) > 0  # type: ignore


def test_get_todays_occupancy_no_occupancy():
    s = service()
    daily = s.get_occupancy("today")
    assert len(daily.lines) == 0
    assert len(daily.events) == 0
    assert daily.occupancy_type is OccupancyType.NONE
    assert isinstance(daily.last_updated, datetime)
    assert daily.error is None
    assert isinstance(daily.date, date)


@pytest.mark.skip("test flaky")
def test_get_todays_week_occupancy_with_occupancy():
    s = service()
    occ = parse_weekly_plan(get_weekly_mock_table())
    occ[
        0
    ].begin = datetime.now()  # HACK: Don't use Datetime with timezone as we can't compare it to the mock data then...
    occ[0].end = occ[0].begin + timedelta(hours=4)
    s._week_occupancy = occ  # type: ignore
    daily = s.get_occupancy("today")
    assert len(daily.lines) > 0
    assert len(daily.events) > 0
    assert len(daily.lines) == len(daily.events)
    assert daily.occupancy_type is OccupancyType.PARTIALLY
    assert daily.occupancy_source is OccupancySource.WEEKLY_PLAN
    assert isinstance(daily.last_updated, datetime)
    assert isinstance(daily.date, date)
    assert daily.error is None


def test_get_todays_calendar_occupancy_with_occupancy():
    s = service()
    occ = parse_event_calendar(get_calendar_mock_table())
    occ[0].begin = datetime.now(tz=ZoneInfo("Europe/Berlin"))
    occ[0].end = occ[0].begin + timedelta(hours=4)
    s._event_occupancy = occ  # type: ignore
    daily = s.get_occupancy("today")
    assert len(daily.lines) > 0
    assert len(daily.events) > 0
    assert len(daily.lines) == len(daily.events)
    assert daily.occupancy_type is OccupancyType.FULLY
    assert daily.occupancy_source is OccupancySource.EVENT_CALENDAR
    assert isinstance(daily.last_updated, datetime)
    assert isinstance(daily.date, date)
    assert daily.error is None


def test_start_and_stop_status_check():
    s = service()
    s.start_polling(interval=1)
    assert s.is_polling
    s.stop_polling()
    assert not s.is_polling
