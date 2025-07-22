import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from app.services.internal.InternalService import InternalService


@pytest.fixture
def service():
    s = InternalService()
    # Avoid threading/rwlock issues by not running threads in these tests
    return s


def test_first_device_on_site_set_when_none_and_new_devices(service: InternalService):
    service._internal_data.first_device_on_site = None  # type: ignore
    service._internal_data.active_devices_ct = 0  # type: ignore
    service._last_updated = datetime.now(tz=ZoneInfo("Europe/Berlin"))  # type: ignore
    service._update_device_statistics(0, 2)  # type: ignore
    assert service._internal_data.first_device_on_site is not None  # type: ignore


def test_first_device_on_site_not_set_when_already_set(service: InternalService):
    now = datetime.now(tz=ZoneInfo("Europe/Berlin"))
    service._internal_data.first_device_on_site = now  # type: ignore
    service._internal_data.active_devices_ct = 0  # type: ignore
    service._last_updated = now  # type: ignore
    service._update_device_statistics(0, 2)  # type: ignore
    assert service._internal_data.first_device_on_site == now  # type: ignore


def test_first_device_on_site_set_when_transition_from_0_to_positive(
    service: InternalService,
):
    service._internal_data.first_device_on_site = None  # type: ignore
    service._internal_data.active_devices_ct = 0  # type: ignore
    service._last_updated = datetime.now(tz=ZoneInfo("Europe/Berlin"))  # type: ignore
    service._update_device_statistics(0, 1)  # type: ignore
    assert service._internal_data.first_device_on_site is not None  # type: ignore


def test_last_device_on_site_set_when_transition_to_zero(service: InternalService):
    service._internal_data.first_device_on_site = datetime.now(tz=ZoneInfo("Europe/Berlin"))  # type: ignore
    service._internal_data.last_device_on_site = None  # type: ignore
    service._internal_data.active_devices_ct = 2  # type: ignore
    service._last_updated = datetime.now(tz=ZoneInfo("Europe/Berlin"))  # type: ignore
    service._update_device_statistics(2, 0)  # type: ignore
    assert service._internal_data.last_device_on_site is not None  # type: ignore


def test_reset_at_5am(service: InternalService):
    # Set last_updated to yesterday before 5am, now after 5am
    yesterday = datetime.now(tz=ZoneInfo("Europe/Berlin")) - timedelta(days=1)
    yesterday = yesterday.replace(hour=4, minute=0, second=0, microsecond=0)
    service._last_updated = yesterday  # type: ignore
    service._internal_data.first_device_on_site = datetime.now(tz=ZoneInfo("Europe/Berlin"))  # type: ignore
    service._internal_data.last_device_on_site = datetime.now(tz=ZoneInfo("Europe/Berlin"))  # type: ignore
    service._internal_data.active_devices_ct = 0  # type: ignore
    service._update_device_statistics(0, 0)  # type: ignore
    assert service._internal_data.first_device_on_site is None  # type: ignore
    assert service._internal_data.last_device_on_site is None  # type: ignore


def test_no_reset_if_same_virtual_day(service: InternalService):
    now = datetime.now(tz=ZoneInfo("Europe/Berlin"))
    service._last_updated = now - timedelta(hours=1)  # type: ignore
    service._internal_data.first_device_on_site = now  # type: ignore
    service._internal_data.last_device_on_site = now  # type: ignore
    service._internal_data.active_devices_ct = 0  # type: ignore
    service._update_device_statistics(0, 0)  # type: ignore
    assert service._internal_data.first_device_on_site == now  # type: ignore
    assert service._internal_data.last_device_on_site == now  # type: ignore
