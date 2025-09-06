import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from os import path
import os
import threading
import time
from typing import Dict, List, Optional, Self
import uuid
from zoneinfo import ZoneInfo
from readerwriterlock import rwlock

from app.services.PersistentCollections import PersistentDict

logger = logging.getLogger("uvicorn.error")


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
    
    def is_outdated(self, days:int):
        return (
            self.valid_until is not None
            and datetime.now(self.valid_until.tzinfo) > self.valid_until + timedelta(days=days)
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
        self._interval_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._rwlock = rwlock.RWLockFair()

    def add(
        self, message: str, valid_from: datetime, valid_until: datetime, enabled: bool
    ) -> str:
        with self._rwlock.gen_wlock():
            nid = str(f"nid-{uuid.uuid4()}")
            notification = Notification(
                created=datetime.now(tz=ZoneInfo("Europe/Berlin")),
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
        elif "all_active" in notification_ids or "latest_active" in notification_ids:
            result = [n for n in self._store.values() if n.is_active()]
        elif "all_enabled" in notification_ids:
            result = [n for n in self._store.values() if n.enabled]
        else:
            requested_ids = {id for id in notification_ids if id.startswith("nid-")}
            result = [n for n in self._store.values() if n.id in requested_ids]

        result.sort(
            key=lambda n: (
                n.created.replace(tzinfo=timezone.utc)
                if n.created.tzinfo is None
                else n.created.astimezone(timezone.utc)
            ),
            reverse=True,
        )

        if "latest_active" in notification_ids:
            result = [result[0]]

        return result

    def list_all(self) -> List[Notification]:
        with self._rwlock.gen_rlock():
            return list(self._store.values())

    def delete(self, nid: str) -> bool:
        with self._rwlock.gen_wlock():
            if nid in self._store:
                del self._store[nid]
                self._store.reload
                return True
            return False

    def update(
        self,
        nid: str,
        enabled: Optional[bool] = None,
        valid_from: Optional[datetime] = None,
        valid_until: Optional[datetime] = None,
    ) -> bool: 
        with self._rwlock.gen_wlock():
            if nid not in self._store:
                return False
            notification = self._store[nid]
            if enabled is not None:
                notification.enabled = enabled
            if valid_from is not None:
                notification.valid_from = valid_from
            if valid_until is not None:
                notification.valid_until = valid_until
            self._store[nid] = notification
            return True

    def get_by_id(self, nid: str) -> Optional[Notification]:
        return self._store.get(nid)
    
    async def _run_clean_old_notifications(self):
        try:
            logger.info(f"Cleaning old notifications...")
            to_delete = [n for n in self.list_all() if n.is_outdated(1)]
            if len(to_delete) > 0:
                logger.info(f"{len(to_delete)} old notifications found, deleting...")
                for notification in to_delete:
                    id = notification.id
                    if self.delete(id):
                        logger.debug(f"deleted notification {id}")
                    else:
                        logger.warning(f"deleting notification {id} failed!")
                else:
                   logger.info(f"No old notifications found.")
            logger.info(f"Cleaning old notifications... DONE")
        except Exception as e:
            logger.error(f"Error during occupancy check: {e}", exc_info=True)

    def _occupancy_loop(self, interval: int):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while not self._stop_event.is_set():
            loop.run_until_complete(self._run_clean_old_notifications())
            time.sleep(interval)

    def start_cleanup_job(self, interval: int = 3600) -> None:
        if self._interval_thread is None or not self._interval_thread.is_alive():
            self._stop_event.clear()
            self._interval_thread = threading.Thread(
                target=self._occupancy_loop,
                args=[interval],
                daemon=True,
            )
            self._interval_thread.start()