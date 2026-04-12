from time import sleep

import pytest

from app.services.occupancy.occupancy_service import OccupancyService


@pytest.mark.skip("test only relevant on manual lookup")
def test_occupancy_service() -> None:
    service = OccupancyService()
    service.start_polling(2)
    sleep(7)
    daily = service.get_occupancy("today")

    assert daily.error is None
