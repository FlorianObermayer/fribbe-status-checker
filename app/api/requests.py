from datetime import datetime

from fastapi import Query
from pydantic import BaseModel, Field, field_validator

from app.services.push_subscription_service import ALL_TOPICS, VALID_TOPICS, PushTopic

# Single source of truth for all keyword filter options.
# Order here determines the order in the UI selector.
NOTIFICATION_FILTERS: list[dict[str, str]] = [
    {"value": "all_active", "label": "Aktive"},
    {"value": "latest_active", "label": "Neueste aktive"},
    {"value": "all_enabled", "label": "Alle aktivierten"},
    {"value": "all_inactive", "label": "Inaktive"},
    {"value": "all", "label": "Alle"},
]

# Keyword IDs that require an authenticated request
_protected_ids = ["all", "all_enabled", "all_inactive"]
# Keyword IDs allowed for unauthenticated requests
_default_ids = ["all_active", "latest_active"]

_keyword_ids = [f["value"] for f in NOTIFICATION_FILTERS]
_examples = [*_keyword_ids, "nid-<...>"]


class NotificationQuery(BaseModel):
    """Query parameters for filtering notifications."""

    n_ids: list[str] = Query(
        examples=[*_examples],
    )

    def filter_unprotected_n_ids(self) -> list[str]:
        """Strip protected filter IDs for unauthenticated requests."""
        result = [n_id for n_id in self.n_ids if n_id not in _protected_ids]
        return result or [_default_ids[0]]

    @field_validator("n_ids", mode="before", check_fields=True)
    @classmethod
    def validate_ids(cls, value: str | list[str]) -> list[str]:
        """Coerce single-string values into a list and validate IDs."""
        if isinstance(value, str):  # Handle single values (e.g., ?q=all_active)
            value = [value]
        for n_id in value:
            if not (n_id in _keyword_ids or n_id.startswith("nid-")):
                msg = f"Invalid ID: '{n_id}'. Must be any or multiple of: [{', '.join(_examples)}]"
                raise ValueError(msg)
        return value


class PushAuthRequest(BaseModel):
    """Request body carrying a push subscription auth token."""

    auth: str


def _validate_topics(v: list[str]) -> list[PushTopic]:
    invalid = set(v) - VALID_TOPICS
    if invalid:
        msg = f"Invalid topics: {sorted(invalid)}"
        raise ValueError(msg)
    if not v:
        msg = "At least one topic is required"
        raise ValueError(msg)
    return sorted(set(v))  # type: ignore[return-value]


class PushSubscribeRequest(BaseModel):
    """Request body for creating a push subscription."""

    endpoint: str
    p256dh: str
    auth: str
    topics: list[PushTopic] = Field(default_factory=lambda: list(ALL_TOPICS))

    @field_validator("topics")
    @classmethod
    def validate_topics(cls, v: list[str]) -> list[PushTopic]:
        """Validate and normalize the topics list."""
        return _validate_topics(v)


class PatchPushTopicsRequest(BaseModel):
    """Request body for updating push subscription topics."""

    auth: str
    topics: list[PushTopic]

    @field_validator("topics")
    @classmethod
    def validate_topics(cls, v: list[str]) -> list[PushTopic]:
        """Validate and normalize the topics list."""
        return _validate_topics(v)


class CreateApiKeyRequest(BaseModel):
    """Request body for creating a new API key."""

    comment: str = ""
    valid_until: datetime | None = None


class DeleteApiKeyRequest(BaseModel):
    """Request body for deleting an API key."""

    key: str


class PostNotificationRequest(BaseModel):
    """Request body for creating a notification."""

    message: str
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    enabled: bool = True


class UpdateNotificationRequest(BaseModel):
    """Request body for updating a notification."""

    enabled: bool | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class ConfigRequest(BaseModel):
    """Request body for updating presence thresholds."""

    threshold_min_non_empty_ct: int | None = Field(None, gt=0)
    threshold_min_many_ct: int | None = Field(None, gt=1)


class CreateWardenRequest(BaseModel):
    """Request body for creating a warden."""

    name: str
    device_macs: list[str] = Field(default_factory=list)
    device_names: list[str] = Field(default_factory=list)


class UpdateWardenRequest(BaseModel):
    """Request body for updating a warden."""

    new_name: str | None = None
    device_macs: list[str] | None = None
    device_names: list[str] | None = None
