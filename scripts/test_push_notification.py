#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["pywebpush>=2.3.0"]
# ///
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


def load_subscriptions(data_path: str) -> list[dict[str, str]]:
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
        print("ERROR: VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, and VAPID_CLAIM_SUBJECT must all be set.")
        sys.exit(1)

    title = sys.argv[1] if len(sys.argv) > 1 else "Fribbe Beach Test 🏐"
    body = sys.argv[2] if len(sys.argv) > 2 else "Das ist eine Test-Benachrichtigung. " + secrets.token_hex(4)

    store_path = Path(data_path) / "push_subscriptions.json"
    subscriptions = load_subscriptions(data_path)
    if not subscriptions:
        print(f"No subscribers found in {store_path}")
        sys.exit(0)

    print(f'Sending to {len(subscriptions)} subscriber(s): "{title}" — "{body}"\n')

    payload = json.dumps({"title": title, "body": body})
    vapid_claims: dict[str, str | int] = {"sub": vapid_claim_subject}

    ok = 0
    stale = 0
    errors = 0

    for sub in subscriptions:
        auth_prefix = sub.get("auth", "?")[:8]
        endpoint = sub.get("endpoint", "")
        host = urlparse(endpoint).netloc or endpoint

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
                print(f"  ✓  {host}  (auth={auth_prefix}...) - (HTTP {result.status_code})")
                ok += 1

        except WebPushException as e:
            status = e.response.status_code if e.response is not None else "?"  # type: ignore[union-attr]
            if e.response is not None and e.response.status_code in (404, 410):  # type: ignore[union-attr]
                print(f"  ✗  {host}  (auth={auth_prefix}...) — stale subscription (HTTP {status})")
                stale += 1
            else:
                print(f"  ✗  {host}  (auth={auth_prefix}...) — HTTP {status}: {e}")
                errors += 1
        except Exception as e:
            print(f"  ✗  {host}  (auth={auth_prefix}...) — {e}")
            errors += 1

    print(f"\nDone: {ok} sent, {stale} stale, {errors} errors")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
