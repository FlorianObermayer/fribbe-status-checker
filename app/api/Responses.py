from datetime import date, datetime
from typing import Dict, List, Self
from pydantic import BaseModel, Field
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
    key: str = Field(..., min_length=20)
    comment: str
    valid_until: datetime

    @classmethod
    def from_dict(cls, d: Dict[str, str]) -> Self:
        return cls(
            key=d["key"],
            comment=d["comment"],
            valid_until=datetime.fromisoformat(d["valid_until"]),
        )

    def to_dict(self) -> Dict[str, str]:
        return {
            "key": self.key,
            "comment": self.comment,
            "valid_until": self.valid_until.isoformat(),
        }


class ApiKeys(BaseModel):
    api_keys: List[ApiKey]


class PostNotificationResponse(BaseModel):
    notification_id: str
