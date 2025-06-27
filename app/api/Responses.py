from datetime import date, datetime
from typing import List
from pydantic import BaseModel
from app.services.PresenceLevelService import PresenceLevel
from app.services.occupancy.Model import Occupancy, OccupancySource, OccupancyType


class BaseResponse(BaseModel):
    last_updated: datetime | None
    last_error: str | None


class PresenceResponse(BaseResponse):
    level: PresenceLevel
    message: str
    thresholds: dict[PresenceLevel, int]


class OccupancyResponse(BaseResponse):
    type: OccupancyType
    source: OccupancySource
    messages: List[str]
    events: List[Occupancy]
    for_date: date


class StatusResponse(BaseModel):
    occupancy: OccupancyResponse
    presence: PresenceResponse


class DetailsResponse(BaseResponse):
    wardens_on_site: List[str]
    active_devices: int
    first_device_on_site: datetime | None
    last_device_on_site: datetime | None
    last_service_start: datetime


class ApiKey(BaseModel):
    key: str
    comment: str | None
    valid_until: datetime | None