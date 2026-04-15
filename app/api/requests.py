from datetime import datetime
from enum import StrEnum

from fastapi import Query
from pydantic import BaseModel, Field, field_validator

from app import env
from app.api.access_role import AccessRole
from app.services.push_subscription_service import PushTopic


class NotificationFilterId(StrEnum):
    """Keyword filter IDs for notification queries."""

    ALL_ACTIVE = "all_active"
    LATEST_ACTIVE = "latest_active"
    ALL_ENABLED = "all_enabled"
    ALL_INACTIVE = "all_inactive"
    ALL = "all"


# Single source of truth for all keyword filter options.
# Order here determines the order in the UI selector.
NOTIFICATION_FILTERS: list[dict[str, str]] = [
    {"value": NotificationFilterId.ALL_ACTIVE.value, "label": "Aktive"},
    {"value": NotificationFilterId.LATEST_ACTIVE.value, "label": "Neueste aktive"},
    {"value": NotificationFilterId.ALL_ENABLED.value, "label": "Alle aktivierten"},
    {"value": NotificationFilterId.ALL_INACTIVE.value, "label": "Inaktive"},
    {"value": NotificationFilterId.ALL.value, "label": "Alle"},
]

# Keyword IDs that require an authenticated request
_protected_ids = [NotificationFilterId.ALL, NotificationFilterId.ALL_ENABLED, NotificationFilterId.ALL_INACTIVE]
# Keyword IDs allowed for unauthenticated requests
_default_ids = [NotificationFilterId.ALL_ACTIVE, NotificationFilterId.LATEST_ACTIVE]

_keyword_ids = [f["value"] for f in NOTIFICATION_FILTERS]
_examples = [*_keyword_ids, "nid-<...>"]


class AuthRedirectQuery(BaseModel):
    """Common query parameters for page requests."""

    next: str = Query(
        default="/",
        description="Optional relative URL to redirect to after successful authentication (e.g., /notification-create)",
    )

    @field_validator("next", mode="before", check_fields=False)
    @classmethod
    def validate_next_url(cls, value: str | None) -> str:
        """Ensure the URLs are safe relative paths."""
        return cls.sanitize_url(value) or "/"

    @staticmethod
    def sanitize_url(value: str | None) -> str | None:
        """Ensure the URLs are safe relative paths."""
        if value is None:
            return value
        if not value.startswith("/") or value.startswith("//"):
            return "/"
        return value


class NotificationQuery(BaseModel):
    """Query parameters for filtering notifications."""

    n_ids: list[NotificationFilterId | str] = Query(
        examples=[*_examples],
    )

    def filter_unprotected_n_ids(self) -> list[str]:
        """Strip protected filter IDs for unauthenticated requests."""
        result = [n_id for n_id in self.n_ids if n_id not in _protected_ids]
        return result or [_default_ids[0]]

    @field_validator("n_ids", mode="before", check_fields=True)
    @classmethod
    def validate_ids(cls, value: NotificationFilterId | str | list[str | NotificationFilterId]) -> list[str]:
        """Coerce single-string values into a list and validate IDs."""
        if isinstance(value, str):  # Handle single values (e.g., ?q=all_active)
            value = [value]
        for n_id in value:
            if not (n_id in _keyword_ids or n_id.startswith("nid-")):
                msg = f"Invalid ID: '{n_id}'. Must be any or multiple of: [{', '.join(_examples)}]"
                raise ValueError(msg)
        return value


class AuthBody(AuthRedirectQuery):
    """Request body for POST /auth."""

    token: str


class PushAuthRequest(BaseModel):
    """Request body carrying a push subscription auth token."""

    auth: str


def _validate_topics(topics: list[str]) -> list[PushTopic]:
    if not topics:
        msg = "At least one topic is required"
        raise ValueError(msg)
    invalid = set(topics) - set(PushTopic)
    if invalid:
        msg = f"Invalid topics: {sorted(invalid)}"
        raise ValueError(msg)
    return list(dict.fromkeys(PushTopic(t) for t in topics))


class PushSubscribeRequest(BaseModel):
    """Request body for creating a push subscription."""

    endpoint: str
    p256dh: str
    auth: str
    topics: list[PushTopic] = Field(default_factory=list[PushTopic])

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
    role: AccessRole = AccessRole.READER


class DeleteApiKeyRequest(BaseModel):
    """Request body for deleting an API key."""

    key: str = Field(
        ...,
        min_length=env.MIN_KEY_PREFIX_LENGTH,
        description=f"Full API key or unique prefix (at least {env.MIN_KEY_PREFIX_LENGTH} characters)",
    )


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
