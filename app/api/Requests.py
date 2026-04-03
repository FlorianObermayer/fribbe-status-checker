import re
from datetime import date
from typing import Any

from fastapi import Query
from pydantic import BaseModel, field_validator

_FORECAST_TOKEN_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

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


class ForecastRequest(BaseModel):
    date: date
    token: str

    @field_validator("token")
    def validate_token(cls, v: str) -> str:
        if not _FORECAST_TOKEN_RE.match(v):
            raise ValueError("token must be a valid lowercase UUID")
        return v
