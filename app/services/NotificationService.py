from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Self
import uuid


@dataclass
class Notification:
    id: str
    message: str
    created: datetime
    valid_until: datetime
    enabled: bool = True

    def is_active(self) -> bool:
        return self.enabled and self.valid_until > datetime.now(self.valid_until.tzinfo)

    def to_dict(self) -> Dict[str, str | bool]:
        return {
            "id": self.id,
            "message": self.message,
            "valid_until": self.valid_until.isoformat(),
            "enabled": self.enabled,
            "created": self.created.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, str | bool]) -> Self:
        return cls(
            id=str(d["id"]),
            message=str(d["message"]),
            valid_until=datetime.fromisoformat(str(d["valid_until"])),
            enabled=bool(d.get("enabled", True)),
            created=datetime.fromisoformat(str(d["created"])),
        )


class NotificationService:
    def __init__(self, persist_path: str = "./notifications.json"):
        self._store: dict[str, Notification] = {}  # TODO: PERSIST

    def add(self, message: str, valid_until: datetime, enabled: bool = True) -> str:
        nid = str(uuid.uuid4())
        notification = Notification(
            created=datetime.now(),
            id=nid,
            message=message,
            valid_until=valid_until,
            enabled=enabled,
        )
        self._store[nid] = notification
        return nid

    def get_active(self) -> List[Notification]:
        result = [n for n in self._store.values() if n.is_active()]
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
