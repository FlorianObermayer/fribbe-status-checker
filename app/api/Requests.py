from datetime import datetime
from typing import Any

from fastapi import Query
from pydantic import BaseModel, Field, field_validator

from app.services.PushSubscriptionService import ALL_TOPICS, VALID_TOPICS, PushTopic

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
    n_ids: list[str] = Query(
        examples=[*_examples],
    )

    def filter_unprotected_n_ids(self):
        result = [n_id for n_id in self.n_ids if n_id not in _protected_ids]
        result = result or [_default_ids[0]]

        return result

    @field_validator("n_ids", mode="before", check_fields=True)
    def validate_ids(cls, value: Any):
        if isinstance(value, str):  # Handle single values (e.g., ?q=all_active)
            value = [value]
        for n_id in value:
            if not (n_id in _keyword_ids or n_id.startswith("nid-")):
                raise ValueError(f"Invalid ID: '{n_id}'. Must be any or multiple of: [{', '.join(_examples)}]")
        return value


class PushAuthRequest(BaseModel):
    auth: str


def _validate_topics(v: list[str]) -> list[PushTopic]:
    invalid = set(v) - VALID_TOPICS
    if invalid:
        raise ValueError(f"Invalid topics: {sorted(invalid)}")
    if not v:
        raise ValueError("At least one topic is required")
    return sorted(set(v))  # type: ignore[return-value]


class PushSubscribeRequest(BaseModel):
    endpoint: str
    p256dh: str
    auth: str
    topics: list[PushTopic] = Field(default_factory=lambda: list(ALL_TOPICS))

    @field_validator("topics")
    @classmethod
    def validate_topics(cls, v: list[str]) -> list[PushTopic]:
        return _validate_topics(v)


class PatchPushTopicsRequest(BaseModel):
    auth: str
    topics: list[PushTopic]

    @field_validator("topics")
    @classmethod
    def validate_topics(cls, v: list[str]) -> list[PushTopic]:
        return _validate_topics(v)


class CreateApiKeyRequest(BaseModel):
    comment: str = ""
    valid_until: datetime | None = None


class DeleteApiKeyRequest(BaseModel):
    key: str


class PostNotificationRequest(BaseModel):
    message: str
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    enabled: bool = True


class UpdateNotificationRequest(BaseModel):
    enabled: bool | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class ConfigRequest(BaseModel):
    threshold_min_non_empty_ct: int | None = Field(None, gt=0)
    threshold_min_many_ct: int | None = Field(None, gt=1)


class CreateWardenRequest(BaseModel):
    name: str
    device_macs: list[str] = Field(default_factory=list)
    device_names: list[str] = Field(default_factory=list)


class UpdateWardenRequest(BaseModel):
    new_name: str | None = None
    device_macs: list[str] | None = None
    device_names: list[str] | None = None
