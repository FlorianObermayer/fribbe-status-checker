# pyright: reportPrivateUsage=false
"""Tests for PresenceLevelService._maybe_send_first_active_push."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.PresenceLevel import PresenceLevel
from app.services.PresenceLevelService import PresenceLevelService


class _FakePushSender:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def send_to_all_sync(self, title: str, body: str) -> None:
        self.calls.append((title, body))


def _make_service(push: _FakePushSender | None = None) -> PresenceLevelService:
    svc = PresenceLevelService()
    if push is not None:
        svc.set_push_service(push)
    return svc


# ---------------------------------------------------------------------------
# First-poll suppression
# ---------------------------------------------------------------------------


def test_first_transition_does_not_send_push():
    """The very first empty→non-empty transition must not fire a push (cold-start guard)."""
    push = _FakePushSender()
    svc = _make_service(push)

    svc._maybe_send_first_active_push(PresenceLevel.EMPTY, PresenceLevel.FEW)

    assert push.calls == []


def test_second_transition_sends_push():
    """After the cold-start guard is cleared, the next transition should fire."""
    push = _FakePushSender()
    svc = _make_service(push)

    # First call arms the guard
    svc._maybe_send_first_active_push(PresenceLevel.EMPTY, PresenceLevel.FEW)
    # Second call should now fire
    svc._maybe_send_first_active_push(PresenceLevel.EMPTY, PresenceLevel.FEW)

    assert len(push.calls) == 1


# ---------------------------------------------------------------------------
# No push when level stays non-empty or transitions downward
# ---------------------------------------------------------------------------


def test_no_push_when_not_transitioning_from_empty():
    push = _FakePushSender()
    svc = _make_service(push)
    svc._push_initialized = True  # skip cold-start guard

    svc._maybe_send_first_active_push(PresenceLevel.FEW, PresenceLevel.MANY)
    svc._maybe_send_first_active_push(PresenceLevel.MANY, PresenceLevel.FEW)
    svc._maybe_send_first_active_push(PresenceLevel.FEW, PresenceLevel.EMPTY)

    assert push.calls == []


# ---------------------------------------------------------------------------
# Once-per-virtual-day deduplication
# ---------------------------------------------------------------------------


def test_second_transition_same_day_does_not_send_again():
    push = _FakePushSender()
    svc = _make_service(push)
    svc._push_initialized = True

    svc._maybe_send_first_active_push(PresenceLevel.EMPTY, PresenceLevel.FEW)
    # Simulate going empty and back active again within the same virtual day
    svc._maybe_send_first_active_push(PresenceLevel.EMPTY, PresenceLevel.FEW)

    assert len(push.calls) == 1


def test_transition_sends_again_on_new_virtual_day():
    push = _FakePushSender()
    svc = _make_service(push)
    svc._push_initialized = True

    # First transition fires and sets _last_push_virtual_date to today
    svc._maybe_send_first_active_push(PresenceLevel.EMPTY, PresenceLevel.FEW)

    # Move last_push_virtual_date two days back → guaranteed to differ from virtual_today
    # (using 2 days because before 05:00 Berlin time the virtual day is already "yesterday")
    berlin = ZoneInfo("Europe/Berlin")
    two_days_ago = (datetime.now(tz=berlin) - timedelta(days=2)).date()
    svc._last_push_virtual_date = two_days_ago

    svc._maybe_send_first_active_push(PresenceLevel.EMPTY, PresenceLevel.MANY)

    assert len(push.calls) == 2


# ---------------------------------------------------------------------------
# Body text selection
# ---------------------------------------------------------------------------


def test_push_body_few():
    push = _FakePushSender()
    svc = _make_service(push)
    svc._push_initialized = True

    svc._maybe_send_first_active_push(PresenceLevel.EMPTY, PresenceLevel.FEW)

    assert push.calls[0][1] == "Ein paar Leute sind schon da!"


def test_push_body_many():
    push = _FakePushSender()
    svc = _make_service(push)
    svc._push_initialized = True

    svc._maybe_send_first_active_push(PresenceLevel.EMPTY, PresenceLevel.MANY)

    assert push.calls[0][1] == "Heute ist richtig was los!"


def test_push_title():
    push = _FakePushSender()
    svc = _make_service(push)
    svc._push_initialized = True

    svc._maybe_send_first_active_push(PresenceLevel.EMPTY, PresenceLevel.FEW)

    assert push.calls[0][0] == "Erster Aufschlag im Fribbe! 🏐"


def test_push_title_many():
    push = _FakePushSender()
    svc = _make_service(push)
    svc._push_initialized = True

    svc._maybe_send_first_active_push(PresenceLevel.EMPTY, PresenceLevel.MANY)

    assert push.calls[0][0] == "Heute ist richtig was los im Fribbe! 🏐"


# ---------------------------------------------------------------------------
# No push when no push service is set
# ---------------------------------------------------------------------------


def test_no_push_without_service():
    svc = _make_service(push=None)
    svc._push_initialized = True

    # Should not raise
    svc._maybe_send_first_active_push(PresenceLevel.EMPTY, PresenceLevel.FEW)
