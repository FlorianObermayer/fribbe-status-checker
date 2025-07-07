from typing import Any, List
from fastapi import Query
from pydantic import BaseModel, field_validator

_protected_ids = ["all", "all_enabled"]
_default_ids = ["all_active", "latest_active"]
_examples = [
    *_protected_ids,
    *_default_ids,
    "nid-<...>",
]
class NotificationQuery(BaseModel):

    n_ids: List[str] = Query(
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
            if not (
                n_id in _protected_ids
                or n_id in _default_ids
                or n_id.startswith("nid-")
            ):
                raise ValueError(
                    f"Invalid ID: '{n_id}'. Must be any or multiple of: [{', '.join(_examples)}]"
                )
        return value
