# pyright: reportPrivateUsage=false
"""Tests for PresenceLevelService._try_send_first_active_push."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.services.message_service import MessageService
from app.services.occupancy.occupancy_service import OccupancyService
from app.services.presence_level import PresenceLevel
from app.services.presence_level_service import PresenceLevelService
from tests.test_utils import FakePushSender


def _make_service(push: FakePushSender | None = None) -> PresenceLevelService:
    return PresenceLevelService(None, MessageService(), push, OccupancyService())


# ---------------------------------------------------------------------------
# First-poll suppression
# ---------------------------------------------------------------------------


def test_first_transition_does_not_send_push() -> None:
    """The very first empty→non-empty transition must not fire a push (cold-start guard)."""
    push = FakePushSender()
    svc = _make_service(push)

    svc._try_send_first_active_push(PresenceLevel.EMPTY, PresenceLevel.FEW)

    assert push.calls == []


def test_second_transition_sends_push() -> None:
    """After the cold-start guard is cleared, the next transition should fire."""
    push = FakePushSender()
    svc = _make_service(push)

    # First call arms the guard
    svc._try_send_first_active_push(PresenceLevel.EMPTY, PresenceLevel.FEW)
    # Second call should now fire
    svc._try_send_first_active_push(PresenceLevel.EMPTY, PresenceLevel.FEW)

    assert len(push.calls) == 1


# ---------------------------------------------------------------------------
# No push when level stays non-empty or transitions downward
# ---------------------------------------------------------------------------


def test_no_push_when_not_transitioning_from_empty() -> None:
    push = FakePushSender()
    svc = _make_service(push)
    svc._push_initialized = True  # skip cold-start guard

    svc._try_send_first_active_push(PresenceLevel.FEW, PresenceLevel.MANY)
    svc._try_send_first_active_push(PresenceLevel.MANY, PresenceLevel.FEW)
    svc._try_send_first_active_push(PresenceLevel.FEW, PresenceLevel.EMPTY)

    assert push.calls == []


# ---------------------------------------------------------------------------
# Once-per-virtual-day deduplication
# ---------------------------------------------------------------------------


def test_second_transition_same_day_does_not_send_again() -> None:
    push = FakePushSender()
    svc = _make_service(push)
    svc._push_initialized = True

    svc._try_send_first_active_push(PresenceLevel.EMPTY, PresenceLevel.FEW)
    # Simulate going empty and back active again within the same virtual day
    svc._try_send_first_active_push(PresenceLevel.EMPTY, PresenceLevel.FEW)

    assert len(push.calls) == 1


def test_transition_sends_again_on_new_virtual_day() -> None:
    push = FakePushSender()
    svc = _make_service(push)
    svc._push_initialized = True

    # First transition fires and sets _last_push_virtual_date to today
    svc._try_send_first_active_push(PresenceLevel.EMPTY, PresenceLevel.FEW)

    # Move last_push_virtual_date two days back → guaranteed to differ from virtual_today
    # (using 2 days because before 05:00 Berlin time the virtual day is already "yesterday")
    berlin = ZoneInfo("Europe/Berlin")
    two_days_ago = (datetime.now(tz=berlin) - timedelta(days=2)).date()
    svc._last_push_virtual_date = two_days_ago

    svc._try_send_first_active_push(PresenceLevel.EMPTY, PresenceLevel.MANY)

    assert len(push.calls) == 2


# ---------------------------------------------------------------------------
# Body text selection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("level", [PresenceLevel.FEW, PresenceLevel.MANY])
def test_push_body(level: PresenceLevel) -> None:
    push = FakePushSender()
    svc = _make_service(push)
    svc._push_initialized = True

    svc._try_send_first_active_push(PresenceLevel.EMPTY, level)  # pyright: ignore[reportUnknownArgumentType]

    assert push.calls[0][0] == "presence"  # topic
    assert push.calls[0][2] is not None  # body


@pytest.mark.parametrize("level", [PresenceLevel.FEW, PresenceLevel.MANY])
def test_push_title(level: PresenceLevel) -> None:
    push = FakePushSender()
    svc = _make_service(push)
    svc._push_initialized = True

    svc._try_send_first_active_push(PresenceLevel.EMPTY, level)  # pyright: ignore[reportUnknownArgumentType]

    assert push.calls[0][1] is not None  # title


# ---------------------------------------------------------------------------
# No push when no push service is set
# ---------------------------------------------------------------------------


def test_no_push_without_service() -> None:
    svc = _make_service(push=None)
    svc._push_initialized = True

    # Should not raise
    svc._try_send_first_active_push(PresenceLevel.EMPTY, PresenceLevel.FEW)
