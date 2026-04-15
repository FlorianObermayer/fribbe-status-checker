import secrets
from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, Field

from app import env
from app.api.access_role import AccessRole
from app.services.internal.model import Warden
from app.services.notification_service import Notification
from app.services.occupancy.model import (
    DailyOccupancy,
    Occupancy,
    OccupancySource,
    OccupancyType,
)
from app.services.presence_level import PresenceLevel
from app.services.push_subscription_service import PushTopic


class BaseResponse(BaseModel):
    """Common fields for poll-based service responses."""

    last_updated: datetime | None
    last_error: str | None


class PresenceResponse(BaseResponse):
    """Presence detection status."""

    level: PresenceLevel
    message: str
    thresholds: dict[PresenceLevel, int]


class OccupancyResponse(BaseResponse):
    """Occupancy information for a given date."""

    type: OccupancyType
    source: OccupancySource
    messages: list[str]
    events: list[Occupancy]
    for_date: date

    @classmethod
    def from_daily(cls, daily: DailyOccupancy) -> "OccupancyResponse":
        """Create an OccupancyResponse from a DailyOccupancy."""
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
    """Combined occupancy and presence status."""

    occupancy: OccupancyResponse
    presence: PresenceResponse


class DetailsResponse(BaseResponse):
    """Detailed internal device-tracking information."""

    wardens_on_site: list[str]
    active_devices: int
    first_device_on_site: datetime | None
    last_device_on_site: datetime | None
    last_service_start: datetime


class ApiKey(BaseModel):
    """An API key with metadata."""

    key: str = Field(..., min_length=env.MIN_TOKEN_LENGTH)
    comment: str = Field(..., max_length=env.COMMENT_MAX_LENGTH)
    valid_until: datetime
    role: AccessRole = AccessRole.ADMIN

    @staticmethod
    def generate_new(comment: str, valid_until: datetime, role: AccessRole = AccessRole.READER) -> "ApiKey":
        """Generate a new cryptographically random API key."""
        n_bytes = env.MIN_TOKEN_LENGTH // 4 * 3  # convert from base64-url string length to raw byte length
        new_key = secrets.token_urlsafe(n_bytes)
        if len(new_key) < env.MIN_TOKEN_LENGTH:
            msg = f"Generated key is too short: {len(new_key)} characters (expected at least {env.MIN_TOKEN_LENGTH})"
            raise ValueError(
                msg,
            )
        return ApiKey(key=new_key, comment=comment, valid_until=valid_until, role=role)

    @classmethod
    def from_dict(cls, d: dict[str, str]) -> Self:
        """Deserialize from a plain dict."""
        raw_role = d.get("role")
        if isinstance(raw_role, int) or (isinstance(raw_role, str) and raw_role.isdigit()):
            role = AccessRole(int(raw_role))
        elif isinstance(raw_role, str):
            # Legacy: stored by name (e.g. "reader"). Fall back to READER on unknown names.
            role = next((r for r in AccessRole if r.name.lower() == raw_role.lower()), AccessRole.READER)
        else:
            role = AccessRole.READER
        return cls(
            key=d["key"],
            comment=d["comment"],
            valid_until=datetime.fromisoformat(d["valid_until"]),
            role=role,
        )

    def to_dict(self) -> dict[str, str]:
        """Serialize to a plain dict."""
        return {
            "key": self.key,
            "comment": self.comment,
            "valid_until": self.valid_until.isoformat(),
            "role": str(self.role.value),
        }


class MaskedApiKey(BaseModel):
    """API key with the raw value replaced by a short prefix."""

    key_prefix: str
    comment: str = Field(..., max_length=env.COMMENT_MAX_LENGTH)
    valid_until: datetime
    role: AccessRole

    @staticmethod
    def from_api_key(api_key: "ApiKey") -> "MaskedApiKey":
        """Create a masked representation of the given API key."""
        return MaskedApiKey(
            key_prefix=MaskedApiKey.get_masked_prefix(api_key.key),
            comment=api_key.comment,
            valid_until=api_key.valid_until,
            role=api_key.role,
        )

    @staticmethod
    def get_masked_prefix(key: str) -> str:
        """Get the masked prefix for a given API key value."""
        return key[: env.MIN_KEY_PREFIX_LENGTH] + "..."


class ApiKeys(BaseModel):
    """Wrapper for a list of masked API keys."""

    api_keys: list[MaskedApiKey]
    self_key_prefix: str | None = None
    admin_token_prefix: str | None = None


class PostNotificationResponse(BaseModel):
    """Response after creating a notification."""

    notification_id: str


class WardenResponse(BaseModel):
    """Public representation of a warden."""

    name: str
    device_macs: list[str]
    device_names: list[str]

    @classmethod
    def from_warden(cls, w: Warden) -> "WardenResponse":
        """Create a response from a Warden domain object."""
        return cls(name=w.name, device_macs=w.device_macs, device_names=w.device_names)


class WardenListResponse(BaseModel):
    """Wrapper for a list of warden responses."""

    wardens: list[WardenResponse]


class VersionResponse(BaseModel):
    """Application version information."""

    version: str


class LicenseEntry(BaseModel):
    """Third-party dependency license information."""

    name: str
    license: str
    url: str


class VapidKeyResponse(BaseModel):
    """Public VAPID key for push subscription."""

    public_key: str


class PushStatusResponse(BaseModel):
    """Current push subscription status for a client."""

    subscribed: bool
    topics: list[PushTopic] = Field(default_factory=list[PushTopic])


class DeletedResponse(BaseModel):
    """Count of deleted resources."""

    deleted: int


class NotificationResponse(BaseModel):
    """Public representation of a notification."""

    id: str
    message: str
    enabled: bool
    created: datetime
    valid_from: datetime | None = None
    valid_until: datetime | None = None

    @classmethod
    def from_notification(cls, n: Notification) -> "NotificationResponse":
        """Create a response from a Notification domain object."""
        return cls(
            id=n.id,
            message=n.message,
            enabled=n.enabled,
            created=n.created,
            valid_from=n.valid_from,
            valid_until=n.valid_until,
        )
