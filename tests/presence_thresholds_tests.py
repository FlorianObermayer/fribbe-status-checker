"""Tests for app.services.presence_thresholds — PresenceLevel mapping."""

from pathlib import Path

import pytest

from app import env
from app.services.presence_level import PresenceLevel
from app.services.presence_thresholds import PresenceThresholds


@pytest.fixture
def thresholds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PresenceThresholds:
    monkeypatch.setattr(env, "LOCAL_DATA_PATH", str(tmp_path))
    return PresenceThresholds()


@pytest.mark.parametrize(
    ("devices_ct", "expected"),
    [
        (0, PresenceLevel.EMPTY),
        (1, PresenceLevel.EMPTY),
        (2, PresenceLevel.FEW),
        (5, PresenceLevel.FEW),
        (9, PresenceLevel.FEW),
        (10, PresenceLevel.MANY),
        (100, PresenceLevel.MANY),
    ],
)
def test_get_presence_level(thresholds: PresenceThresholds, devices_ct: int, expected: PresenceLevel) -> None:
    assert thresholds.get_presence_level(devices_ct) == expected


def test_setter_persists_min_non_empty_ct(thresholds: PresenceThresholds) -> None:
    thresholds.min_non_empty_ct = 5
    assert thresholds.min_non_empty_ct == 5
    assert thresholds.get_presence_level(4) == PresenceLevel.EMPTY
    assert thresholds.get_presence_level(5) == PresenceLevel.FEW


def test_setter_persists_min_many_ct(thresholds: PresenceThresholds) -> None:
    thresholds.min_many_ct = 20
    assert thresholds.min_many_ct == 20
    assert thresholds.get_presence_level(19) == PresenceLevel.FEW
    assert thresholds.get_presence_level(20) == PresenceLevel.MANY
