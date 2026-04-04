import json
import logging
import re
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Self
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from pywebpush import WebPushException, webpush  # type: ignore[import-untyped]

import app.env as env
from app.services.PersistentCollections import PersistentDict

logger = logging.getLogger("uvicorn.error")

_B64URL_RE = re.compile(r"^[A-Za-z0-9\-_]+=*$")


@dataclass
class PushSubscription:
    endpoint: str
    p256dh: str
    auth: str
    created: datetime

    def to_dict(self) -> dict[str, str]:
        return {
            "endpoint": self.endpoint,
            "p256dh": self.p256dh,
            "auth": self.auth,
            "created": self.created.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, str]) -> Self:
        return cls(
            endpoint=str(d["endpoint"]),
            p256dh=str(d["p256dh"]),
            auth=str(d["auth"]),
            created=datetime.fromisoformat(str(d["created"])),
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
        if not _B64URL_RE.match(auth) or len(auth) < 10:
            raise ValueError("invalid auth")

    def add(self, endpoint: str, p256dh: str, auth: str) -> None:
        sub = PushSubscription(
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            created=datetime.now(tz=ZoneInfo("Europe/Berlin")),
        )
        self._store[auth] = sub

    def remove(self, auth: str) -> bool:
        if auth not in self._store:
            return False
        del self._store[auth]
        return True

    def send_to_all_sync(self, title: str, body: str) -> None:
        """Send a push notification to all subscribers. Removes expired subscriptions."""
        payload = json.dumps({"title": title, "body": body})
        stale: list[str] = []
        for auth, sub in list(self._store.items()):
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
