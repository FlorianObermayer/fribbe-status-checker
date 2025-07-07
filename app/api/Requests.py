from typing import Any, List
from fastapi import Query
from pydantic import BaseModel, field_validator


class NotificationQuery(BaseModel):

    @staticmethod
    def _protected_ids() -> List[str]:
        return ["all"]

    @staticmethod
    def _default_ids() -> List[str]:
        return ["all_active"]

    n_ids: List[str] = Query(
        examples=[_protected_ids(), _default_ids(), "nid-<123>"],
    )

    def filter_unprotected_n_ids(self):
        result = [
            n_id
            for n_id in self.n_ids
            if n_id not in NotificationQuery._protected_ids()
        ]
        result = result or [*NotificationQuery._default_ids()]

        return result

    @field_validator("n_ids", mode="before", check_fields=True)
    def validate_ids(cls, value: Any):
        if isinstance(value, str):  # Handle single values (e.g., ?q=all_active)
            value = [value]
        for n_id in value:
            if not (
                n_id in NotificationQuery._protected_ids()
                or n_id in NotificationQuery._default_ids()
                or n_id.startswith("nid-")
            ):
                raise ValueError(
                    f"Invalid ID: '{n_id}'. Must be 'all', 'all_active', or start with 'nid-'"
                )
        return value
