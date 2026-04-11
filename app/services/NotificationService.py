import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Self
from zoneinfo import ZoneInfo

import app.env as env
from app.services.PersistentCollections import PersistentDict
from app.services.PollingService import PollingService

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
            and (self.valid_from is None or datetime.now(self.valid_from.tzinfo) >= self.valid_from)
            and (self.valid_until is None or datetime.now(self.valid_until.tzinfo) < self.valid_until)
        )

    def is_outdated(self, days: int):
        return self.valid_until is not None and datetime.now(self.valid_until.tzinfo) > self.valid_until + timedelta(
            days=days
        )

    def to_dict(self) -> dict[str, str | bool]:
        result: dict[str, str | bool] = {
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
    def from_dict(cls, d: dict[str, str | bool]) -> Self:
        return cls(
            id=str(d["id"]),
            message=str(d["message"]),
            valid_from=(datetime.fromisoformat(str(d["valid_from"])) if d.get("valid_from") else None),
            valid_until=(datetime.fromisoformat(str(d["valid_until"])) if d.get("valid_until") else None),
            enabled=bool(d.get("enabled", True)),
            created=datetime.fromisoformat(str(d["created"])),
        )


class NotificationService(PollingService):
    def __init__(self):
        super().__init__()
        self._store: PersistentDict[Notification] = PersistentDict(
            str(Path(env.LOCAL_DATA_PATH) / "notifications.json"),
            value_type=Notification,
        )

    def add(self, message: str, valid_from: datetime | None, valid_until: datetime | None, enabled: bool) -> str:
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

    def get(self, notification_ids: list[str] | None = None) -> list[Notification]:
        if notification_ids is None:
            notification_ids = ["all_active"]
        result: list[Notification] = []

        if "all" in notification_ids:
            result = [*self._store.values()]
        elif "all_active" in notification_ids or "latest_active" in notification_ids:
            result = [n for n in self._store.values() if n.is_active()]
        elif "all_enabled" in notification_ids:
            result = [n for n in self._store.values() if n.enabled]
        elif "all_inactive" in notification_ids:
            result = [n for n in self._store.values() if not n.is_active()]
        else:
            requested_ids = {id for id in notification_ids if id.startswith("nid-")}
            result = [n for n in self._store.values() if n.id in requested_ids]

        result.sort(
            key=lambda n: n.created.replace(tzinfo=UTC) if n.created.tzinfo is None else n.created.astimezone(UTC),
            reverse=True,
        )

        if "latest_active" in notification_ids:
            result = [result[0]] if len(result) > 0 else []

        return result

    def list_all(self) -> list[Notification]:
        return list(self._store.values())

    def delete(self, nid: str) -> bool:
        with self._store.batch_write() as store:
            if nid in store:
                del store[nid]
                return True
            return False

    def delete_many(self, nids: list[str]) -> int:
        with self._store.batch_write() as store:
            if "all" in nids:
                count = len(store)
                store.clear()
                return count

            if "all_active" in nids:
                to_delete = [n.id for n in store.values() if n.is_active()]
            elif "all_enabled" in nids:
                to_delete = [n.id for n in store.values() if n.enabled]
            elif "all_inactive" in nids:
                to_delete = [n.id for n in store.values() if not n.is_active()]
            else:
                requested = {nid for nid in nids if nid.startswith("nid-")}
                to_delete = [nid for nid in requested if nid in store]

            for nid in to_delete:
                del store[nid]
            return len(to_delete)

    def update(
        self,
        nid: str,
        enabled: bool | None = None,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
    ) -> bool:
        with self._store.batch_write() as store:
            if nid not in store:
                return False
            notification = store[nid]
            if enabled is not None:
                notification.enabled = enabled
            if valid_from is not None:
                notification.valid_from = valid_from
            if valid_until is not None:
                notification.valid_until = valid_until
            store[nid] = notification
            return True

    def get_by_id(self, nid: str) -> Notification | None:
        return self._store.get(nid)

    async def _run_poll(self) -> None:
        await self._run_clean_old_notifications()

    async def _run_clean_old_notifications(self):
        try:
            logger.info("Cleaning old notifications...")
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
                logger.info("No old notifications found.")
            logger.info("Cleaning old notifications... DONE")
        except Exception as e:
            logger.error(f"Error during notification cleanup: {e}", exc_info=True)

    def start_cleanup_job(self, interval: int = 3600) -> None:
        self.start_polling(interval)
