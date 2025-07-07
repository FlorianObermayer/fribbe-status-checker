from dataclasses import dataclass
from datetime import datetime
from os import path
import os
from typing import Dict, List, Optional, Self
import uuid

from app.services.PersistentCollections import PersistentDict


@dataclass
class Notification:
    id: str
    message: str
    created: datetime
    valid_from: datetime | None
    valid_until: datetime | None
    enabled: bool

    def is_active(self) -> bool:
        return (
            self.enabled
            and (
                self.valid_from is None
                or datetime.now(self.valid_from.tzinfo) >= self.valid_from
            )
            and (
                self.valid_until is None
                or datetime.now(self.valid_until.tzinfo) < self.valid_until
            )
        )

    def to_dict(self) -> Dict[str, str | bool]:
        result: Dict[str, str | bool] = {
            "id": self.id,
            "message": self.message,
            "enabled": self.enabled,
            "created": self.created.isoformat(),
        }

        if self.valid_from:
            result["valid_from"] = self.valid_from.isoformat()

        if self.valid_until:
            result["valid_until"] = self.valid_until.isoformat()

        return result

    @classmethod
    def from_dict(cls, d: Dict[str, str | bool]) -> Self:
        return cls(
            id=str(d["id"]),
            message=str(d["message"]),
            valid_from=(
                datetime.fromisoformat(str(d["valid_from"]))
                if d.get("valid_from")
                else None
            ),
            valid_until=(
                datetime.fromisoformat(str(d["valid_until"]))
                if d.get("valid_until")
                else None
            ),
            enabled=bool(d.get("enabled", True)),
            created=datetime.fromisoformat(str(d["created"])),
        )


class NotificationService:

    def __init__(self):
        self._store: PersistentDict[Notification] = PersistentDict(
            path.join(os.environ["LOCAL_DATA_PATH"], "notifications.json"),
            value_type=Notification,
        )

    def add(
        self, message: str, valid_from: datetime, valid_until: datetime, enabled: bool
    ) -> str:
        nid = str(f"nid-{uuid.uuid4()}")
        notification = Notification(
            created=datetime.now(),
            id=nid,
            message=message,
            valid_from=valid_from,
            valid_until=valid_until,
            enabled=enabled,
        )
        self._store[nid] = notification
        return nid

    def get(self, notification_ids: List[str] = ["all_active"]) -> List[Notification]:
        result: List[Notification] = []

        if "all" in notification_ids:
            result = [*self._store.values()]
        elif "all_active" in notification_ids:
            return [n for n in self._store.values() if n.is_active()]
        else:
            requested_ids = {id for id in notification_ids if id.startswith("nid-")}
            result = [n for n in self._store.values() if n.id in requested_ids]

        result.sort(key=lambda n: n.created, reverse=True)
        return result

    def list_all(self) -> List[Notification]:
        return list(self._store.values())

    def delete(self, nid: str) -> bool:
        if nid in self._store:
            del self._store[nid]
            return True
        return False

    def update(
        self,
        nid: str,
        enabled: Optional[bool] = None,
        valid_until: Optional[datetime] = None,
    ) -> bool:
        if nid not in self._store:
            return False
        notification = self._store[nid]
        if enabled is not None:
            notification.enabled = enabled
        if valid_until is not None:
            notification.valid_until = valid_until
        self._store[nid] = notification
        return True

    def get_by_id(self, nid: str) -> Optional[Notification]:
        return self._store.get(nid)
