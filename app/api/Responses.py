from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, Field

from app.services.occupancy.Model import Occupancy, OccupancySource, OccupancyType
from app.services.PresenceLevel import PresenceLevel


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
    messages: list[str]
    events: list[Occupancy]
    for_date: date


class StatusResponse(BaseModel):
    occupancy: OccupancyResponse
    presence: PresenceResponse


class DetailsResponse(BaseResponse):
    wardens_on_site: list[str]
    active_devices: int
    first_device_on_site: datetime | None
    last_device_on_site: datetime | None
    last_service_start: datetime


class ApiKey(BaseModel):
    key: str = Field(..., min_length=48)
    comment: str
    valid_until: datetime

    @classmethod
    def from_dict(cls, d: dict[str, str]) -> Self:
        return cls(
            key=d["key"],
            comment=d["comment"],
            valid_until=datetime.fromisoformat(d["valid_until"]),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "comment": self.comment,
            "valid_until": self.valid_until.isoformat(),
        }


class ApiKeys(BaseModel):
    api_keys: list[ApiKey]


class PostNotificationResponse(BaseModel):
    notification_id: str


class WardenResponse(BaseModel):
    name: str
    device_macs: list[str]
    device_names: list[str]


class WardenListResponse(BaseModel):
    wardens: list[WardenResponse]


class ForecastResponse(BaseModel):
    count: int
    committed: bool
