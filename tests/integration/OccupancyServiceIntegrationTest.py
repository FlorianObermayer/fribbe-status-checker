from time import sleep

import pytest

from app.services.occupancy.OccupancyService import OccupancyService


@pytest.mark.skip("test only relevant on manual lookup")
def test_occupancy_service():
    service = OccupancyService()
    service.start_polling(2)
    sleep(7)
    daily = service.get_occupancy("today")

    print(
        f"message: {daily.lines}, events: {daily.events}, for_date: {daily.date}, type: {daily.occupancy_type}, source: {daily.occupancy_source}, last_updated: {daily.last_updated}"
    )
    assert daily.error is None
