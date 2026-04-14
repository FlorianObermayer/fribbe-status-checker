import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Self
from zoneinfo import ZoneInfo

import markdown
import nh3

from app import env
from app.api.requests import NotificationFilterId
from app.services.persistent_collections import PersistentDict
from app.services.polling_service import PollingService
from app.services.push_sender import PushSender

logger = logging.getLogger("uvicorn.error")

_PUSH_TITLE = "Neues aus'm Fribbe"
_MAX_PUSH_LENGTH = 200


def _push_message(markdown_text: str) -> str:
    """Convert Markdown to plain text for push notification bodies."""
    html = markdown.markdown(markdown_text)
    sanitized = nh3.clean(html)
    stripped = re.sub(r"<[^>]+>", "", sanitized)
    # limit to 200 chars for push notifications, as some platforms have limits and we want to avoid cutting in the middle of a word
    if len(stripped) > _MAX_PUSH_LENGTH:
        stripped = stripped[: _MAX_PUSH_LENGTH - 1]
        # cut off any trailing incomplete word
        stripped = re.sub(r"\s+\S*$", "", stripped)
        # add ellipsis to indicate truncation
        stripped += "…"
    return stripped.strip()


@dataclass
class Notification:
    """A user-created notification with optional scheduling."""

    id: str
    message: str
    created: datetime
    valid_from: datetime | None
    valid_until: datetime | None
    enabled: bool

    def is_active(self) -> bool:
        """Return True if the notification is enabled and within its time window."""
        return (
            self.enabled
            and (self.valid_from is None or datetime.now(self.valid_from.tzinfo) >= self.valid_from)
            and (self.valid_until is None or datetime.now(self.valid_until.tzinfo) < self.valid_until)
        )

    def is_outdated(self, days: int) -> bool:
        """Return True if valid_until has passed by more than the given days."""
        return self.valid_until is not None and datetime.now(self.valid_until.tzinfo) > self.valid_until + timedelta(
            days=days,
        )

    def to_dict(self) -> dict[str, str | bool]:
        """Serialize to a plain dict."""
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
        """Deserialize from a plain dict."""
        return cls(
            id=str(d["id"]),
            message=str(d["message"]),
            valid_from=(datetime.fromisoformat(str(d["valid_from"])) if d.get("valid_from") else None),
            valid_until=(datetime.fromisoformat(str(d["valid_until"])) if d.get("valid_until") else None),
            enabled=bool(d.get("enabled", True)),
            created=datetime.fromisoformat(str(d["created"])),
        )


class NotificationService(PollingService):
    """Manage notifications with optional push delivery and periodic cleanup."""

    def __init__(self, push_sender: PushSender | None = None) -> None:
        super().__init__()
        self._push_sender = push_sender
        self._known_active_nids: set[str] | None = None  # None until first poll; avoids re-pushing on startup
        self._store: PersistentDict[Notification] = PersistentDict(
            str(Path(env.LOCAL_DATA_PATH) / "notifications.json"),
            value_type=Notification,
        )

    def add(self, message: str, valid_from: datetime | None, valid_until: datetime | None, *, enabled: bool) -> str:
        """Create a notification, send a push if active, and return its ID."""
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
        if notification.is_active() and self._push_sender is not None:
            self._push_sender.send_to_topic_sync("notifications", _PUSH_TITLE, _push_message(message))
            known_active_nids = self._known_active_nids
            if known_active_nids is not None:
                self._known_active_nids = {*known_active_nids, nid}
        return nid

    def get(self, notification_ids: list[str] | None = None) -> list[Notification]:
        """Return notifications matching the given filter IDs."""
        if notification_ids is None:
            notification_ids = [NotificationFilterId.ALL_ACTIVE]
        result: list[Notification] = []

        if NotificationFilterId.ALL in notification_ids:
            result = [*self._store.values()]
        elif (
            NotificationFilterId.ALL_ACTIVE in notification_ids
            or NotificationFilterId.LATEST_ACTIVE in notification_ids
        ):
            result = [n for n in self._store.values() if n.is_active()]
        elif NotificationFilterId.ALL_ENABLED in notification_ids:
            result = [n for n in self._store.values() if n.enabled]
        elif NotificationFilterId.ALL_INACTIVE in notification_ids:
            result = [n for n in self._store.values() if not n.is_active()]
        else:
            requested_ids = {nid for nid in notification_ids if nid.startswith("nid-")}
            result = [n for n in self._store.values() if n.id in requested_ids]

        result.sort(
            key=lambda n: n.created.replace(tzinfo=UTC) if n.created.tzinfo is None else n.created.astimezone(UTC),
            reverse=True,
        )

        if NotificationFilterId.LATEST_ACTIVE in notification_ids:
            result = [result[0]] if len(result) > 0 else []

        return result

    def list_all(self) -> list[Notification]:
        """Return all stored notifications."""
        return list(self._store.values())

    def delete(self, nid: str) -> bool:
        """Delete a notification by ID; return True if found."""
        with self._store.batch_write() as store:
            if nid in store:
                del store[nid]
                return True
            return False

    def delete_many(self, nids: list[str]) -> int:
        """Delete notifications matching the given filter IDs; return the count."""
        with self._store.batch_write() as store:
            if NotificationFilterId.ALL in nids:
                count = len(store)
                store.clear()
                return count

            if NotificationFilterId.ALL_ACTIVE in nids:
                to_delete = [n.id for n in store.values() if n.is_active()]
            elif NotificationFilterId.ALL_ENABLED in nids:
                to_delete = [n.id for n in store.values() if n.enabled]
            elif NotificationFilterId.ALL_INACTIVE in nids:
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
        *,
        enabled: bool | None = None,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
    ) -> bool:
        """Update fields of an existing notification; return True if found."""
        with self._store.batch_write() as store:
            if nid not in store:
                return False
            notification = store[nid]
            was_active = notification.is_active()
            if enabled is not None:
                notification.enabled = enabled
            if valid_from is not None:
                notification.valid_from = valid_from
            if valid_until is not None:
                notification.valid_until = valid_until
            store[nid] = notification
            if not was_active and notification.is_active() and self._push_sender is not None:
                self._push_sender.send_to_topic_sync("notifications", _PUSH_TITLE, _push_message(notification.message))
                if self._known_active_nids is not None:
                    self._known_active_nids = set(self._known_active_nids) | {nid}
            return True

    def get_by_id(self, nid: str) -> Notification | None:
        """Return a notification by ID, or None."""
        return self._store.get(nid)

    async def _run_poll(self) -> None:
        await self._check_newly_active_notifications()
        await self._run_clean_old_notifications()

    async def _check_newly_active_notifications(self) -> None:
        """Fire push notifications for notifications that became active since the last poll."""
        if self._push_sender is None:
            return
        current_active = {n.id for n in self._store.values() if n.is_active()}
        if self._known_active_nids is None:
            # First poll - record current state without pushing to avoid re-notifying on startup
            self._known_active_nids = current_active
            return
        newly_active = current_active - self._known_active_nids
        self._known_active_nids = current_active
        for nid in newly_active:
            notification = self._store.get(nid)
            if notification is not None:
                logger.info("Notification %s became active - sending push", nid)
                self._push_sender.send_to_topic_sync("notifications", _PUSH_TITLE, _push_message(notification.message))

    async def _run_clean_old_notifications(self) -> None:
        try:
            logger.info("Cleaning old notifications...")
            to_delete = [n for n in self.list_all() if n.is_outdated(1)]
            if len(to_delete) > 0:
                logger.info("%d old notifications found, deleting...", len(to_delete))
                for notification in to_delete:
                    nid = notification.id
                    if self.delete(nid):
                        logger.debug("deleted notification %s", nid)
                    else:
                        logger.warning("deleting notification %s failed!", nid)
            else:
                logger.info("No old notifications found.")
            logger.info("Cleaning old notifications... DONE")
        except Exception:
            logger.exception("Error during notification cleanup")

    def start_cleanup_job(self, interval: int = 60) -> None:
        """Begin periodic cleanup of outdated notifications."""
        self.start_polling(interval)
