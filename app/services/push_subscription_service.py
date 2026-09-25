import ipaddress
import json
import logging
import re
import socket
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Self
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests
from pywebpush import WebPushException, webpush  # type: ignore[import-untyped]

from app.config import cfg
from app.services.persistent_collections import PersistentDict

logger = logging.getLogger(__name__)

_B64URL_RE = re.compile(r"^[A-Za-z0-9\-_]+=*$")

# Minimum base64url-encoded length for Web Push key fields (p256dh, auth).
# Real values are longer (p256dh ≈ 87 chars, auth ≈ 22 chars); this is a
# conservative lower bound to reject obviously invalid input.
_MIN_PUSH_KEY_LENGTH = 10

# Maximum number of stored push subscriptions. The store is unauthenticated and
# every subscribe rewrites the whole JSON file, so an unbounded store lets an
# anonymous caller consume disk space and grow the per-request rewrite cost
# without limit.
_MAX_SUBSCRIPTIONS = 1000

# Maximum time (seconds) to wait for a single push service request before abandoning it.
_PUSH_REQUEST_TIMEOUT_SECONDS = 10


# Push requests must never be redirected: a public endpoint could otherwise
# bounce the server to an internal address after validation has passed.
_PUSH_SESSION = requests.Session()
_PUSH_SESSION.max_redirects = 0


def _resolve_push_host(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolve *host* to every IPv4/IPv6 address it maps to."""
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return [ipaddress.ip_address(info[4][0]) for info in infos]


def _validate_endpoint(endpoint: str) -> None:
    """Reject endpoints that are not https URLs pointing at a public host."""
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.netloc:
        msg = "endpoint must be a valid https URL"
        raise ValueError(msg)
    if parsed.username or parsed.password:
        msg = "endpoint must not contain userinfo"
        raise ValueError(msg)
    host = parsed.hostname
    if not host:
        msg = "endpoint must be a valid https URL"
        raise ValueError(msg)
    try:
        addresses = _resolve_push_host(host)
    except OSError as e:
        msg = "endpoint host could not be resolved"
        raise ValueError(msg) from e
    if not addresses or not all(address.is_global for address in addresses):
        msg = "endpoint must resolve to a public address"
        raise ValueError(msg)


class PushTopic(StrEnum):
    """Push notification topic identifiers."""

    PRESENCE = "presence"
    NOTIFICATIONS = "notifications"


@dataclass
class PushSubscription:
    """A Web Push subscription record."""

    endpoint: str
    p256dh: str
    auth: str
    created: datetime
    topics: list[PushTopic] = field(default_factory=lambda: list(PushTopic))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "endpoint": self.endpoint,
            "p256dh": self.p256dh,
            "auth": self.auth,
            "created": self.created.isoformat(),
            "topics": self.topics,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        """Deserialize from a plain dict."""
        raw_topics: list[str] = list(d.get("topics") or PushTopic)
        valid_topics: list[PushTopic] = [PushTopic(t) for t in raw_topics if t in frozenset(PushTopic)]
        return cls(
            endpoint=str(d["endpoint"]),
            p256dh=str(d["p256dh"]),
            auth=str(d["auth"]),
            created=datetime.fromisoformat(str(d["created"])),
            topics=valid_topics or list(PushTopic),
        )


class PushSubscriptionService:
    """Manage Web Push subscriptions and send notifications via VAPID."""

    def __init__(self, vapid_private_key: str, vapid_public_key: str, vapid_claim_subject: str) -> None:
        self._vapid_private_key = vapid_private_key
        self._vapid_public_key = vapid_public_key
        self._vapid_claims: dict[str, str | int] = {"sub": vapid_claim_subject}
        self._store: PersistentDict[PushSubscription] = PersistentDict(
            str(Path(cfg.LOCAL_DATA_PATH) / "push_subscriptions.json"),
            value_type=PushSubscription,
        )

    def get_public_key(self) -> str:
        """Return the VAPID public key for client-side subscription."""
        return self._vapid_public_key

    @staticmethod
    def validate_subscription(endpoint: str, p256dh: str, auth: str) -> None:
        """Validate subscription fields. Raise ValueError on invalid input."""
        _validate_endpoint(endpoint)
        if not _B64URL_RE.match(p256dh) or len(p256dh) < _MIN_PUSH_KEY_LENGTH:
            msg = "invalid p256dh"
            raise ValueError(msg)
        PushSubscriptionService.validate_auth(auth)

    @staticmethod
    def validate_auth(auth: str) -> None:
        """Validate auth field. Raise ValueError on invalid input."""
        if not _B64URL_RE.match(auth) or len(auth) < _MIN_PUSH_KEY_LENGTH:
            msg = "invalid auth"
            raise ValueError(msg)

    def add(self, endpoint: str, p256dh: str, auth: str, topics: list[PushTopic] | None = None) -> None:
        """Register or replace a push subscription.

        Raise ValueError when the store is full and *auth* is a new subscription.
        """
        if auth not in self._store and len(self._store) >= _MAX_SUBSCRIPTIONS:
            msg = "subscription limit reached"
            raise ValueError(msg)
        sub = PushSubscription(
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            created=datetime.now(tz=ZoneInfo(cfg.TZ)),
            topics=list(topics) if topics is not None else list(PushTopic),
        )
        self._store[auth] = sub

    def has(self, auth: str) -> bool:
        """Return True if a subscription with the given auth exists."""
        return auth in self._store

    def remove(self, auth: str) -> bool:
        """Remove a subscription by auth; return True if found."""
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
                    requests_session=_PUSH_SESSION,
                    timeout=_PUSH_REQUEST_TIMEOUT_SECONDS,
                )
                logger.info("Push sent to subscription %s...", auth[:8])
            except WebPushException as e:
                if e.response is not None and e.response.status_code in (404, 410):  # pyright: ignore[reportUnknownMemberType]
                    stale.append(auth)
                    logger.info("Stale push subscription %s... (HTTP %s)", auth[:8], e.response.status_code)  # pyright: ignore[reportUnknownMemberType]
                else:
                    logger.exception("Push notification failed for %s...", auth[:8])
            except Exception:
                logger.exception("Unexpected push error for %s...", auth[:8])
        for auth in stale:
            with suppress(KeyError):
                del self._store[auth]
