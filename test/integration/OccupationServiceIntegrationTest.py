from time import sleep

from app.services.occupancy.OccupancyService import OccupancyService

def test_occupation_service():
    service = OccupancyService()
    service.start_polling(2)
    sleep(7)
    (message, type, source, last_updated, last_error) = service.get_todays_occupancy()

    print(
        f"message: {message}, type: {type}, source: {source}, last_updated: {last_updated}"
    )
    assert last_error is None
