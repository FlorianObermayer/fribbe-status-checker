from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from app.services.internal.internal_service import InternalService


@pytest.fixture
def service() -> InternalService:
    return InternalService()
    # Avoid threading/rwlock issues by not running threads in these tests


def test_first_device_on_site_set_when_none_and_new_devices(service: InternalService) -> None:
    service._internal_data.first_device_on_site = None
    service._internal_data.active_devices_ct = 0
    service._last_updated = datetime.now(tz=ZoneInfo("Europe/Berlin"))
    service._update_device_statistics(0, 2)
    assert service._internal_data.first_device_on_site is not None


def test_first_device_on_site_not_set_when_already_set(service: InternalService) -> None:
    now = datetime.now(tz=ZoneInfo("Europe/Berlin"))
    service._internal_data.first_device_on_site = now
    service._internal_data.active_devices_ct = 0
    service._last_updated = now
    service._update_device_statistics(0, 2)
    assert service._internal_data.first_device_on_site == now


def test_first_device_on_site_set_when_transition_from_0_to_positive(
    service: InternalService,
) -> None:
    service._internal_data.first_device_on_site = None
    service._internal_data.active_devices_ct = 0
    service._last_updated = datetime.now(tz=ZoneInfo("Europe/Berlin"))
    service._update_device_statistics(0, 1)
    assert service._internal_data.first_device_on_site is not None


def test_last_device_on_site_set_when_transition_to_zero(service: InternalService) -> None:
    service._internal_data.first_device_on_site = datetime.now(tz=ZoneInfo("Europe/Berlin"))
    service._internal_data.last_device_on_site = None
    service._internal_data.active_devices_ct = 2
    service._last_updated = datetime.now(tz=ZoneInfo("Europe/Berlin"))
    service._update_device_statistics(2, 0)
    assert service._internal_data.last_device_on_site is not None


def test_reset_at_5am(service: InternalService) -> None:
    # Set last_updated to yesterday before 5am, now after 5am
    yesterday = datetime.now(tz=ZoneInfo("Europe/Berlin")) - timedelta(days=1)
    yesterday = yesterday.replace(hour=4, minute=0, second=0, microsecond=0)
    service._last_updated = yesterday
    service._internal_data.first_device_on_site = datetime.now(tz=ZoneInfo("Europe/Berlin"))
    service._internal_data.last_device_on_site = datetime.now(tz=ZoneInfo("Europe/Berlin"))
    service._internal_data.active_devices_ct = 0
    service._update_device_statistics(0, 0)
    assert service._internal_data.first_device_on_site is None
    assert service._internal_data.last_device_on_site is None


def test_no_reset_if_same_virtual_day(service: InternalService) -> None:
    # Use a fixed time well away from the 5 AM boundary so the test is deterministic
    now = datetime(2026, 4, 15, 14, 0, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    service._last_updated = now - timedelta(hours=1)
    service._internal_data.first_device_on_site = now
    service._internal_data.last_device_on_site = now
    service._internal_data.active_devices_ct = 0
    with patch("app.services.internal.internal_service.datetime") as mock_dt:
        mock_dt.now.return_value = now
        service._update_device_statistics(0, 0)
    assert service._internal_data.first_device_on_site == now
    assert service._internal_data.last_device_on_site == now
