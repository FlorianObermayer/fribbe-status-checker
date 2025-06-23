import pytest
from datetime import datetime
import os
from unittest.mock import MagicMock, patch
import zoneinfo

from app.OccupancyService import OccupancyService, OccupancyType
from test.test_utils import get_mock_table


def service():
    url = os.environ.get("OCCUPANCY_URL", "http://dummy")
    return OccupancyService(url)


def test_parse_table_returns_occupancies():
    s = service()
    table = get_mock_table()
    occupancies = s._parse_table(table)  # type: ignore
    assert len(occupancies) > 0
    assert any(o.event == "Hobbygruppe" for o in occupancies)


def test_parse_table_skips_empty_events():
    s = service()
    table = get_mock_table()
    occupancies = s._parse_table(table)  # type: ignore
    assert not any(o.day == "Dienstag" for o in occupancies)


@pytest.mark.asyncio
@patch("app.OccupancyService.OccupancyService._get_occupancy_data")
async def test_run_get_latest_occupancy_sets_week_occupancy(
    mock_get_occupancy_data: MagicMock,
):
    s = service()
    mock_get_occupancy_data.return_value = get_mock_table()
    await s._run_get_latest_occupancy()  # type: ignore
    assert hasattr(s, "_week_occupancy")
    assert len(s._week_occupancy) > 0  # type: ignore


def test_get_todays_occupancy_no_occupancy():
    s = service()
    s._week_occupancy = []  # type: ignore
    msg, occupation, last_updated = s.get_todays_occupancy()
    assert "keine Feldbelegungen" in msg
    assert occupation is OccupancyType.NONE
    assert isinstance(last_updated, datetime)


def test_get_todays_occupancy_with_occupancy():
    s = service()
    today = datetime.now(zoneinfo.ZoneInfo("Europe/Berlin")).strftime("%A")
    occ = s._parse_table(get_mock_table())  # type: ignore
    occ[0].day = today
    occ[0].__post_init__()  # Recompute times
    s._week_occupancy = occ  # type: ignore
    msg, occupancy, last_updated = s.get_todays_occupancy()
    assert "Belegung heute" in msg
    assert isinstance(occupancy, OccupancyType)
    assert isinstance(last_updated, datetime)


def test_start_and_stop_status_check():
    s = service()
    s._interval_thread = None  # type: ignore
    s.start_status_check(interval=1)
    assert s._interval_thread.is_alive()  # type: ignore
    s.stop_status_check()
    assert not (s._interval_thread and s._interval_thread.is_alive())  # type: ignore
