"""Send a test push notification to all current subscribers.

Reads VAPID keys and the subscription store from the same environment variables
and data path that the app uses, so the easiest way to run it is:

    # from the repo root, with your .env loaded:
    LOCAL_DATA_PATH=dev-data/app-data/ \
    VAPID_PRIVATE_KEY=... \
    VAPID_PUBLIC_KEY=... \
    VAPID_CLAIM_SUBJECT=... \
    uv run scripts/test_push_notification.py

Or pass a custom title / body:

    uv run scripts/test_push_notification.py "My title" "My body text"
"""

import json
import secrets
import sys
from pathlib import Path
from urllib.parse import urlparse

from pywebpush import Response, WebPushException, webpush  # type: ignore[import-untyped]

from app import env


def load_subscriptions(data_path: str | Path) -> list[dict[str, str]]:
    store_path = Path(data_path) / "push_subscriptions.json"
    if not store_path.exists():
        return []
    with store_path.open(encoding="utf-8") as f:
        raw: dict[str, dict[str, str]] = json.load(f)
    return list(raw.values())


def main() -> None:

    env.load()
    vapid_private_key = env.VAPID_PRIVATE_KEY
    vapid_public_key = env.VAPID_PUBLIC_KEY
    vapid_claim_subject = env.VAPID_CLAIM_SUBJECT
    data_path = env.LOCAL_DATA_PATH

    if not vapid_private_key or not vapid_public_key or not vapid_claim_subject:
        sys.exit(1)

    title = sys.argv[1] if len(sys.argv) > 1 else "Fribbe Beach Test 🏐"
    body = sys.argv[2] if len(sys.argv) > 2 else "Das ist eine Test-Benachrichtigung. " + secrets.token_hex(4)  # noqa: PLR2004

    subscription_path = Path(data_path) / "push_subscriptions.json"
    subscriptions = load_subscriptions(subscription_path)
    if not subscriptions:
        sys.exit(0)

    payload = json.dumps({"title": title, "body": body})
    vapid_claims: dict[str, str | int] = {"sub": vapid_claim_subject}

    ok = 0
    stale = 0
    errors = 0

    for sub in subscriptions:
        sub.get("auth", "?")[:8]
        endpoint = sub.get("endpoint", "")
        _ = urlparse(endpoint).netloc or endpoint

        try:
            result = webpush(
                subscription_info={
                    "endpoint": endpoint,
                    "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
                },
                data=payload,
                vapid_private_key=vapid_private_key,
                vapid_claims=dict(vapid_claims),
            )

            if isinstance(result, Response):
                result.raise_for_status()
                ok += 1

        except WebPushException as e:
            if e.response is not None and e.response.status_code in (404, 410):  # type: ignore[union-attr]
                stale += 1
            else:
                errors += 1
        except Exception:
            errors += 1

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
