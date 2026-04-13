"""Tests for app.dependencies lifecycle (startup / shutdown)."""

from unittest.mock import MagicMock, patch

import pytest

import app.dependencies as deps
from tests.test_utils import reset_dependency_singletons


@pytest.fixture(autouse=True)
def reset_singletons() -> None:
    """Ensure every test starts with a clean slate and pollers are stopped."""
    reset_dependency_singletons()


# ---------------------------------------------------------------------------
# startup
# ---------------------------------------------------------------------------


@patch("app.dependencies.OccupancyService", autospec=True)
@patch("app.dependencies.InternalService", autospec=True)
@patch("app.dependencies.MessageService", autospec=True)
@patch("app.dependencies.NotificationService", autospec=True)
@patch("app.dependencies.PresenceLevelService", autospec=True)
@patch("app.dependencies.env")
def test_startup_creates_services_and_starts_pollers(  # noqa: PLR0913
    mock_env: MagicMock,
    mock_presence_cls: MagicMock,
    mock_notification_cls: MagicMock,
    mock_message_cls: MagicMock,
    mock_internal_cls: MagicMock,
    mock_occupancy_cls: MagicMock,
) -> None:
    mock_env.OPENWEATHERMAP_API_KEY = None
    mock_env.WEATHER_LAT = None
    mock_env.WEATHER_LON = None
    mock_env.VAPID_PRIVATE_KEY = None
    mock_env.VAPID_PUBLIC_KEY = None
    mock_env.VAPID_CLAIM_SUBJECT = None
    mock_env.OCCUPANCY_POLLING_INTERVAL_SECONDS = 360
    mock_env.ROUTER_IP = "192.168.1.1"
    mock_env.ROUTER_USERNAME = "admin"
    mock_env.ROUTER_PASSWORD = "secret"  # noqa: S105
    mock_env.INTERNAL_POLLING_INTERVAL_SECONDS = 60
    mock_env.INTERNAL_POLLING_DELAY_SECONDS = 30
    mock_env.PRESENCE_POLLING_INTERVAL_SECONDS = 60
    mock_env.PRESENCE_POLLING_DELAY_SECONDS = 0
    mock_env.is_presence_enabled.return_value = True
    mock_env.is_push_enabled.return_value = False
    mock_env.is_weather_enabled.return_value = False

    deps.startup()

    mock_env.validate.assert_called_once()
    mock_occupancy_cls.return_value.start_polling.assert_called_once_with(360)
    mock_internal_cls.return_value.start_polling.assert_called_once()
    mock_message_cls.assert_called_once()
    mock_notification_cls.return_value.start_cleanup_job.assert_called_once()
    mock_presence_cls.return_value.start_polling.assert_called_once()

    # Public getters should now succeed (services are wired up)
    assert deps.get_occupancy_service() is not None
    assert deps.get_internal_service() is not None
    assert deps.get_message_service() is not None
    assert deps.get_notification_service() is not None
    assert deps.get_presence_service() is not None


# ---------------------------------------------------------------------------
# shutdown
# ---------------------------------------------------------------------------


@patch("app.dependencies.OccupancyService", autospec=True)
@patch("app.dependencies.InternalService", autospec=True)
@patch("app.dependencies.NotificationService", autospec=True)
@patch("app.dependencies.PresenceLevelService", autospec=True)
@patch("app.dependencies.env")
def test_shutdown_stops_all_pollers(
    mock_env: MagicMock,
    mock_presence_cls: MagicMock,
    mock_notification_cls: MagicMock,
    mock_internal_cls: MagicMock,
    mock_occupancy_cls: MagicMock,
) -> None:
    mock_env.OPENWEATHERMAP_API_KEY = None
    mock_env.WEATHER_LAT = None
    mock_env.WEATHER_LON = None
    mock_env.VAPID_PRIVATE_KEY = None
    mock_env.VAPID_PUBLIC_KEY = None
    mock_env.VAPID_CLAIM_SUBJECT = None
    mock_env.OCCUPANCY_POLLING_INTERVAL_SECONDS = 360
    mock_env.ROUTER_IP = "192.168.1.1"
    mock_env.ROUTER_USERNAME = "admin"
    mock_env.ROUTER_PASSWORD = "secret"  # noqa: S105
    mock_env.INTERNAL_POLLING_INTERVAL_SECONDS = 60
    mock_env.INTERNAL_POLLING_DELAY_SECONDS = 30
    mock_env.PRESENCE_POLLING_INTERVAL_SECONDS = 60
    mock_env.PRESENCE_POLLING_DELAY_SECONDS = 0
    mock_env.is_presence_enabled.return_value = True
    mock_env.is_push_enabled.return_value = False
    mock_env.is_weather_enabled.return_value = False

    deps.startup()
    deps.shutdown()

    mock_occupancy_cls.return_value.stop_polling.assert_called_once()
    mock_internal_cls.return_value.stop_polling.assert_called_once()
    mock_notification_cls.return_value.stop_polling.assert_called_once()
    mock_presence_cls.return_value.stop_polling.assert_called_once()


def test_shutdown_tolerates_none_services() -> None:
    deps.shutdown()  # should not raise


# ---------------------------------------------------------------------------
# Getter guards
# ---------------------------------------------------------------------------


def test_getters_raise_before_startup() -> None:
    with pytest.raises(RuntimeError, match="Services not initialized"):
        deps.get_occupancy_service()
    with pytest.raises(RuntimeError, match="Services not initialized"):
        deps.get_internal_service()
    with pytest.raises(RuntimeError, match="Services not initialized"):
        deps.get_message_service()
    with pytest.raises(RuntimeError, match="Services not initialized"):
        deps.get_notification_service()
    with pytest.raises(RuntimeError, match="Services not initialized"):
        deps.get_presence_service()


def test_weather_getter_returns_none_before_startup() -> None:
    assert deps.get_weather_service() is None
