from time import sleep
import pytest

from app.services.occupancy.OccupancyService import OccupancyService


@pytest.mark.skip("test only relevant on manual lookup")
def test_occupancy_service():
    service = OccupancyService()
    service.start_polling(2)
    sleep(7)
    (for_date, message, events, type, source, last_updated, last_error) = (
        service.get_occupancy("today")
    )

    print(
        f"message: {message}, events: {events}, for_date: {for_date}, type: {type}, source: {source}, last_updated: {last_updated}"
    )
    assert last_error is None
