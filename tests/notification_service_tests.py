# pyright: reportPrivateUsage=false
"""Tests for push notification behaviour in NotificationService."""

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.api.requests import NotificationFilterId
from app.config import cfg
from app.services.notification_service import _PUSH_TITLE, NotificationService, _push_message
from tests.test_utils import FakePushSender

_TZ = ZoneInfo("Europe/Berlin")
_NOW = datetime.now(tz=_TZ)
_FUTURE = _NOW + timedelta(hours=2)


def _make_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    push: FakePushSender | None = None,
) -> NotificationService:
    monkeypatch.setattr(cfg, "LOCAL_DATA_PATH", str(tmp_path))
    return NotificationService(push_sender=push)


# ---------------------------------------------------------------------------
# _push_message
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("markdown_text", "expected"),
    [
        # Plain text passes through unchanged
        ("Hello world", "Hello world"),
        # Markdown bold/italic stripped
        ("Hello **world**", "Hello world"),
        ("_emphasized_", "emphasized"),
        # Inline HTML sanitized, then tags stripped
        ("<b>bold</b>", "bold"),
        ('<script>alert("xss")</script>', ""),
        # & in plain text stays as &amp; (markdown doesn't decode entities outside HTML context)
        ("a &amp; b", "a &amp; b"),
        # Leading/trailing whitespace removed
        ("  hello  ", "hello"),
        # Exactly 200 chars — no truncation
        ("a" * 200, "a" * 200),
        # 201 chars — truncated with ellipsis
        ("a" * 201, "a" * 199 + "…"),
        # Long text cut at word boundary, not mid-word
        ("word " * 41, "word " * 38 + "word…"),
    ],
)
def test_push_message(markdown_text: str, expected: str) -> None:
    assert _push_message(markdown_text) == expected


# ---------------------------------------------------------------------------
# add() — immediate push
# ---------------------------------------------------------------------------


def test_add_sends_push_when_notification_is_active(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    push = FakePushSender()
    svc = _make_service(tmp_path, monkeypatch, push)

    svc.add("Hallo **Welt**", None, None, enabled=True)

    assert len(push.calls) == 1
    topic, title, body = push.calls[0]
    assert topic == "notifications"
    assert title == _PUSH_TITLE
    assert "Hallo" in body
    assert "<" not in body  # HTML tags must be stripped


def test_add_skips_push_when_notification_is_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    push = FakePushSender()
    svc = _make_service(tmp_path, monkeypatch, push)

    svc.add("Test", None, None, enabled=False)

    assert push.calls == []


def test_add_skips_push_when_valid_from_is_in_future(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    push = FakePushSender()
    svc = _make_service(tmp_path, monkeypatch, push)

    svc.add("Test", _FUTURE, None, enabled=True)

    assert push.calls == []


def test_add_skips_push_when_no_push_sender(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    svc = _make_service(tmp_path, monkeypatch, push=None)

    nid = svc.add("Test", None, None, enabled=True)  # must not raise

    assert svc.get([nid])[0].is_active()


# ---------------------------------------------------------------------------
# update() — transition push
# ---------------------------------------------------------------------------


def test_update_sends_push_when_notification_becomes_active(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    push = FakePushSender()
    svc = _make_service(tmp_path, monkeypatch, push)
    svc.add("Hallo Welt", None, None, enabled=False)  # no push (disabled)
    nid = svc.list_all()[0].id
    push.calls.clear()

    svc.update(nid, enabled=True)

    assert len(push.calls) == 1
    assert push.calls[0][0] == "notifications"


def test_update_skips_push_when_already_active(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    push = FakePushSender()
    svc = _make_service(tmp_path, monkeypatch, push)
    svc.add("Hallo Welt", None, None, enabled=True)
    nid = svc.list_all()[0].id
    push.calls.clear()

    svc.update(nid, enabled=True)  # already active — no new push

    assert push.calls == []


def test_update_skips_push_when_no_push_sender(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    svc = _make_service(tmp_path, monkeypatch, push=None)
    svc.add("Test", None, None, enabled=False)
    nid = svc.list_all()[0].id

    svc.update(nid, enabled=True)  # must not raise


# ---------------------------------------------------------------------------
# polling — future notifications becoming active
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_poll_sends_push_for_newly_active_notification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    push = FakePushSender()
    svc = _make_service(tmp_path, monkeypatch, push)
    # Add an inactive notification
    svc.add("Test", None, None, enabled=False)
    nid = svc.list_all()[0].id

    # First poll: initializes _known_active_nids with empty set (notification is inactive)
    await svc._check_newly_active_notifications()
    assert push.calls == []
    assert svc._known_active_nids == set()

    # Simulate the notification becoming active externally (e.g. valid_from passed)
    # by bypassing update() to avoid triggering update()'s own push path
    svc._store[nid].enabled = True

    # Second poll: detects the transition
    await svc._check_newly_active_notifications()

    assert len(push.calls) == 1
    assert push.calls[0][0] == "notifications"


@pytest.mark.asyncio
async def test_poll_first_run_does_not_push_for_already_active(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    push = FakePushSender()
    svc = _make_service(tmp_path, monkeypatch, push)
    svc.add("Bereits aktiv", None, None, enabled=True)
    push.calls.clear()

    # First poll must not re-push already-active notifications
    await svc._check_newly_active_notifications()

    assert push.calls == []


@pytest.mark.asyncio
async def test_poll_skips_when_no_push_sender(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    svc = _make_service(tmp_path, monkeypatch, push=None)
    svc.add("Test", None, None, enabled=True)

    await svc._check_newly_active_notifications()  # must not raise


# ---------------------------------------------------------------------------
# delete_many
# ---------------------------------------------------------------------------


def test_delete_many_all_clears_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:

    svc = _make_service(tmp_path, monkeypatch)
    svc.add("first", None, None, enabled=True)
    svc.add("second", None, None, enabled=False)

    count = svc.delete_many([NotificationFilterId.ALL])

    assert count == 2
    assert svc.list_all() == []


def test_delete_many_all_active_deletes_only_active(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:

    svc = _make_service(tmp_path, monkeypatch)
    svc.add("active msg", None, None, enabled=True)
    svc.add("disabled msg", None, None, enabled=False)

    count = svc.delete_many([NotificationFilterId.ALL_ACTIVE])

    assert count == 1
    remaining = svc.list_all()
    assert len(remaining) == 1
    assert remaining[0].message == "disabled msg"


def test_delete_many_by_specific_nid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    svc = _make_service(tmp_path, monkeypatch)
    svc.add("hello", None, None, enabled=True)
    nid = svc.list_all()[0].id

    count = svc.delete_many([nid])

    assert count == 1
    assert svc.list_all() == []


def test_delete_many_nonexistent_nid_returns_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    svc = _make_service(tmp_path, monkeypatch)

    count = svc.delete_many(["nid-does-not-exist"])

    assert count == 0


# ---------------------------------------------------------------------------
# _run_clean_old_notifications
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_clean_old_notifications_deletes_outdated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    svc = _make_service(tmp_path, monkeypatch)
    past = _NOW - timedelta(days=2)
    svc.add("outdated", None, past, enabled=True)

    await svc._run_clean_old_notifications()

    assert svc.list_all() == []


@pytest.mark.asyncio
async def test_run_clean_old_notifications_keeps_active(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    svc = _make_service(tmp_path, monkeypatch)
    svc.add("still active", None, _FUTURE, enabled=True)

    await svc._run_clean_old_notifications()

    assert len(svc.list_all()) == 1
