"""Tests for MessageService.get_season and get_daytime helpers."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.message_service import MessageService

_TZ = ZoneInfo("Europe/Berlin")


@pytest.mark.parametrize(
    ("month", "expected_season"),
    [
        (1, "winter"),
        (2, "winter"),
        (3, "spring"),
        (4, "spring"),
        (5, "spring"),
        (6, "summer"),
        (7, "summer"),
        (8, "summer"),
        (9, "autumn"),
        (10, "autumn"),
        (11, "autumn"),
        (12, "winter"),
    ],
)
def test_get_season(month: int, expected_season: str) -> None:
    svc = MessageService()
    dt = datetime(2026, month, 15, 12, 0, tzinfo=_TZ)
    assert svc.get_season(dt) == expected_season


@pytest.mark.parametrize(
    ("hour", "expected_daytime"),
    [
        (0, "night"),
        (4, "night"),
        (5, "morning"),
        (9, "morning"),
        (10, "day"),
        (15, "day"),
        (16, "evening"),
        (21, "evening"),
        (22, "night"),
        (23, "night"),
    ],
)
def test_get_daytime(hour: int, expected_daytime: str) -> None:
    svc = MessageService()
    dt = datetime(2026, 6, 15, hour, 0, tzinfo=_TZ)
    assert svc.get_daytime(dt) == expected_daytime
