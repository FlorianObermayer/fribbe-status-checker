import secrets
from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, Field

from app import env
from app.services.occupancy.Model import (
    DailyOccupancy,
    Occupancy,
    OccupancySource,
    OccupancyType,
)
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

    @classmethod
    def from_daily(cls, daily: DailyOccupancy) -> "OccupancyResponse":
        return cls(
            last_updated=daily.last_updated,
            last_error=str(daily.error) if daily.error is not None else None,
            type=daily.occupancy_type,
            source=daily.occupancy_source,
            messages=daily.lines,
            events=daily.events,
            for_date=daily.date,
        )


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
    key: str = Field(..., min_length=env.MIN_TOKEN_LENGTH)
    comment: str
    valid_until: datetime

    @staticmethod
    def generate_new(comment: str, valid_until: datetime) -> "ApiKey":
        n_bytes = env.MIN_TOKEN_LENGTH // 4 * 3  # convert from base64-url string length to raw byte length
        new_key = secrets.token_urlsafe(n_bytes)
        if len(new_key) < env.MIN_TOKEN_LENGTH:
            raise ValueError(
                f"Generated key is too short: {len(new_key)} characters (expected at least {env.MIN_TOKEN_LENGTH})"
            )
        return ApiKey(key=new_key, comment=comment, valid_until=valid_until)

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
