
import os
from time import sleep

from app.services.occupancy.OccupancyService import OccupancyService

def test_occupation_service():
    weekly_plan_url = os.environ["WEEKLY_PLAN_URL"]
    event_calendar_url = os.environ["EVENT_CALENDAR_URL"]
    service = OccupancyService(weekly_plan_url, event_calendar_url)
    service.start_status_check(2)
    sleep(7)
    (message, type, last_updated, last_error) = service.get_todays_occupancy()

    print(f"message: {message}, type: {type}, last_updated: {last_updated}")
    assert last_error is None
