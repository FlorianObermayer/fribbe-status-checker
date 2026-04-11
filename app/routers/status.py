from fastapi import APIRouter

from app.api.Responses import OccupancyResponse, PresenceResponse, StatusResponse
from app.dependencies import MessageServiceDep, OccupancyServiceDep, PresenceServiceDep, WeatherServiceDep
from app.services.occupancy.Model import OccupancyType
from app.services.PresenceThresholds import PresenceThresholds

router = APIRouter(prefix="/api/status", tags=["Status"])


@router.get("", response_model=StatusResponse)
async def get_status(
    occupancy_svc: OccupancyServiceDep,
    presence_svc: PresenceServiceDep,
    message_svc: MessageServiceDep,
    weather_svc: WeatherServiceDep,
    for_date: str = "today",
) -> StatusResponse:
    daily_occupancy = occupancy_svc.get_occupancy(for_date)
    occupancy_response = OccupancyResponse.from_daily(daily_occupancy)

    time_str = next(
        (event.time_str for event in daily_occupancy.events if event.occupancy_type == OccupancyType.FULLY),
        None,
    )
    weather = weather_svc.get_condition() if weather_svc is not None else None
    presence_level = presence_svc.get_level()
    presence_last_updated = presence_svc.get_last_updated()
    presence_message = message_svc.get_status_message(
        presence_level, daily_occupancy.occupancy_type, time_str, weather
    ).message
    presence_last_error = presence_svc.get_last_error()

    presence_response = PresenceResponse(
        level=presence_level,
        last_updated=presence_last_updated,
        message=presence_message,
        last_error=presence_last_error and str(presence_last_error),
        thresholds=PresenceThresholds().get_thresholds(),
    )

    return StatusResponse(
        occupancy=occupancy_response,
        presence=presence_response,
    )
