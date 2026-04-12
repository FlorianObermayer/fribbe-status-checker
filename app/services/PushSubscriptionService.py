import json
import logging
import re
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Self, get_args
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from pywebpush import WebPushException, webpush  # type: ignore[import-untyped]

import app.env as env
from app.services.PersistentCollections import PersistentDict

logger = logging.getLogger("uvicorn.error")

_B64URL_RE = re.compile(r"^[A-Za-z0-9\-_]+=*$")

PushTopic = Literal["presence", "notifications"]
VALID_TOPICS: frozenset[PushTopic] = frozenset(get_args(PushTopic))
ALL_TOPICS: list[PushTopic] = sorted(VALID_TOPICS)


@dataclass
class PushSubscription:
    endpoint: str
    p256dh: str
    auth: str
    created: datetime
    topics: list[PushTopic] = field(default_factory=lambda: list(ALL_TOPICS))

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "p256dh": self.p256dh,
            "auth": self.auth,
            "created": self.created.isoformat(),
            "topics": self.topics,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        raw_topics: list[str] = list(d.get("topics") or ALL_TOPICS)
        valid_topics: list[PushTopic] = [t for t in raw_topics if t in VALID_TOPICS]  # type: ignore[reportUnknownVariableType]
        return cls(
            endpoint=str(d["endpoint"]),
            p256dh=str(d["p256dh"]),
            auth=str(d["auth"]),
            created=datetime.fromisoformat(str(d["created"])),
            topics=valid_topics or list(ALL_TOPICS),
        )


class PushSubscriptionService:
    def __init__(self, vapid_private_key: str, vapid_public_key: str, vapid_claim_subject: str):
        self._vapid_private_key = vapid_private_key
        self._vapid_public_key = vapid_public_key
        self._vapid_claims: dict[str, str | int] = {"sub": vapid_claim_subject}
        self._store: PersistentDict[PushSubscription] = PersistentDict(
            str(Path(env.LOCAL_DATA_PATH) / "push_subscriptions.json"),
            value_type=PushSubscription,
        )

    def get_public_key(self) -> str:
        return self._vapid_public_key

    @staticmethod
    def validate_subscription(endpoint: str, p256dh: str, auth: str) -> None:
        """Validates subscription fields. Raises ValueError on invalid input."""
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("endpoint must be a valid https URL")
        if not _B64URL_RE.match(p256dh) or len(p256dh) < 10:
            raise ValueError("invalid p256dh")
        PushSubscriptionService.validate_auth(auth)

    @staticmethod
    def validate_auth(auth: str) -> None:
        """Validates auth field. Raises ValueError on invalid input."""
        if not _B64URL_RE.match(auth) or len(auth) < 10:
            raise ValueError("invalid auth")

    def add(self, endpoint: str, p256dh: str, auth: str, topics: list[PushTopic] | None = None) -> None:
        sub = PushSubscription(
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            created=datetime.now(tz=ZoneInfo("Europe/Berlin")),
            topics=list(topics) if topics is not None else list(ALL_TOPICS),
        )
        self._store[auth] = sub

    def has(self, auth: str) -> bool:
        return auth in self._store

    def remove(self, auth: str) -> bool:
        if auth not in self._store:
            return False
        del self._store[auth]
        return True

    def get_topics(self, auth: str) -> list[PushTopic]:
        """Return the topics for a subscription, or an empty list if not found."""
        if auth not in self._store:
            return []
        return list(self._store[auth].topics)

    def update_topics(self, auth: str, topics: list[PushTopic]) -> bool:
        """Update topics for an existing subscription. Returns False if not found."""
        with self._store.batch_write() as store:
            if auth not in store:
                return False
            store[auth].topics = list(topics)
            return True

    def send_to_topic_sync(self, topic: PushTopic, title: str, body: str) -> None:
        """Send a push notification to subscribers of a specific topic. Removes expired subscriptions."""
        payload = json.dumps({"title": title, "body": body})
        stale: list[str] = []
        for auth, sub in list(self._store.items()):
            if topic not in sub.topics:
                continue
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                    },
                    data=payload,
                    vapid_private_key=self._vapid_private_key,
                    vapid_claims=dict(self._vapid_claims),
                )
                logger.info(f"Push sent to subscription {auth[:8]}...")
            except WebPushException as e:
                if e.response is not None and e.response.status_code in (404, 410):  # pyright: ignore[reportUnknownMemberType]
                    stale.append(auth)
                    logger.info(f"Stale push subscription {auth[:8]}... (HTTP {e.response.status_code})")  # pyright: ignore[reportUnknownMemberType]
                else:
                    logger.error(f"Push notification failed for {auth[:8]}...: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"Unexpected push error for {auth[:8]}...: {e}", exc_info=True)
        for auth in stale:
            with suppress(KeyError):
                del self._store[auth]
