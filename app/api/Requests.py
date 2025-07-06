from typing import Any, List
from fastapi import Query
from pydantic import BaseModel, field_validator

class NotificationQuery(BaseModel):
    notification_ids: List[str] = Query(
        alias="notification_ids",
        examples=["all", "all_valid", "nid-<123>"],
    )

    @field_validator("notification_ids", mode="before", check_fields=True)
    def validate_ids(cls, value:Any):
        if isinstance(value, str):  # Handle single values (e.g., ?q=all_valid)
            value = [value]
        for id_ in value:
            if not (id_ in {"all", "all_valid"} or id_.startswith("nid-")):
                raise ValueError(
                    f"Invalid ID: '{id_}'. Must be 'all', 'all_valid', or start with 'nid-'"
                )
        return value