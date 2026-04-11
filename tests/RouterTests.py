"""HTTP-level tests for all routers.

Each test overrides exactly the service getters it needs via
``test_app.dependency_overrides`` (set up by the function-scoped ``client``
fixture in conftest.py).  The TestClient resolves dependencies through
FastAPI's normal DI machinery, so no monkey-patching of globals is required.

Auth-protected endpoints are exercised with a fixed admin token injected via
``monkeypatch.setattr(env, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)`` and sent as
the ``api_key`` request header.
"""

from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.env as env
from app.api.EphemeralAPIKeyStore import EphemeralAPIKeyStore
from app.api.Responses import ApiKey
from app.dependencies import (
    get_internal_service,
    get_message_service,
    get_notification_service,
    get_occupancy_service,
    get_presence_service,
    get_push_subscription_service,
    get_weather_service,
)
from app.services.MessageService import StatusMessage
from app.services.NotificationService import Notification
from app.services.occupancy.Model import DailyOccupancy, OccupancySource, OccupancyType
from app.services.PresenceLevel import PresenceLevel
from tests.conftest import TEST_ADMIN_TOKEN

_UTC = ZoneInfo("UTC")
_NOW = datetime(2026, 4, 11, 12, 0, 0, tzinfo=_UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _daily_occupancy(occupancy_type: OccupancyType = OccupancyType.NONE) -> DailyOccupancy:
    return DailyOccupancy(
        date=date(2026, 4, 11),
        lines=[],
        events=[],
        occupancy_type=occupancy_type,
        occupancy_source=OccupancySource.WEEKLY_PLAN,
        last_updated=_NOW,
        error=None,
    )


def _mock_occupancy_svc(occupancy_type: OccupancyType = OccupancyType.NONE) -> MagicMock:
    svc = MagicMock()
    svc.get_occupancy.return_value = _daily_occupancy(occupancy_type)
    return svc


def _mock_presence_svc(level: PresenceLevel = PresenceLevel.EMPTY) -> MagicMock:
    svc = MagicMock()
    svc.get_level.return_value = level
    svc.get_last_updated.return_value = _NOW
    svc.get_last_error.return_value = None
    return svc


def _mock_message_svc(message: str = "Niemand da") -> MagicMock:
    svc = MagicMock()
    svc.get_status_message.return_value = StatusMessage(message=message)
    return svc


def _mock_internal_svc() -> MagicMock:
    svc = MagicMock()
    svc.get_last_updated.return_value = _NOW
    svc.get_last_error.return_value = None
    svc.get_wardens_on_site.return_value = []
    svc.get_active_devices_ct.return_value = 0
    svc.get_first_device_on_site.return_value = None
    svc.get_last_device_on_site.return_value = None
    svc.get_last_service_started.return_value = _NOW
    return svc


def _mock_notification_svc() -> MagicMock:
    return MagicMock()


def _get_session_cookie_value(client: TestClient) -> str:
    """Return the raw session cookie value (opaque starsessions ID)."""
    cookie_value = client.cookies.get("session_cookie")
    assert cookie_value is not None
    return cookie_value


def _get_csrf_headers(client: TestClient) -> dict[str, str]:
    """Read the CSRF token from the ``csrftoken`` cookie set by starlette-csrf."""
    csrf_cookie = client.cookies.get("csrftoken")
    assert csrf_cookie is not None, "csrftoken cookie not set — make a GET request first"
    return {"x-csrf-token": csrf_cookie}


# ---------------------------------------------------------------------------
# /auth (page login)
# ---------------------------------------------------------------------------


def test_post_auth_accepts_admin_token(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(env, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)

    response = client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})

    assert response.status_code == 200
    assert response.json()["redirect"] == "/"
    session_cookie = _get_session_cookie_value(client)
    assert TEST_ADMIN_TOKEN not in session_cookie


def test_post_auth_api_key_uses_opaque_session_cookie(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    keys_path = tmp_path / "api_keys.json"
    monkeypatch.setattr(env, "API_KEYS_PATH", str(keys_path))
    api_key = ApiKey.generate_new(comment="test", valid_until=datetime(2026, 12, 31, tzinfo=_UTC))
    assert EphemeralAPIKeyStore.append(api_key)

    response = client.post("/auth", json={"token": api_key.key, "next": "/"})

    assert response.status_code == 200
    session_cookie = _get_session_cookie_value(client)
    assert api_key.key not in session_cookie


def test_post_auth_rejects_wrong_token(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(env, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)

    response = client.post("/auth", json={"token": "wrong-token", "next": "/"})

    assert response.status_code == 401


def test_post_auth_admin_token_grants_api_access(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Logging in via the form with ADMIN_TOKEN should allow access to protected API endpoints."""
    monkeypatch.setattr(env, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    test_app.dependency_overrides[get_internal_service] = lambda: _mock_internal_svc()

    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})

    response = client.get("/api/internal/details")
    assert response.status_code == 200


def test_get_auth_page_renders_password_field(client: TestClient) -> None:
    response = client.get("/auth")

    assert response.status_code == 200
    assert 'id="auth-form"' in response.text
    assert 'type="password"' in response.text


def test_get_auth_page_includes_csrf_cookie_when_signed_in(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(env, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})

    response = client.get("/auth")

    assert response.status_code == 200
    assert client.cookies.get("csrftoken") is not None


def test_signout_rejects_missing_csrf_for_session_auth(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(env, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})

    response = client.post("/signout")

    assert response.status_code == 403


def test_signout_accepts_valid_csrf_for_session_auth(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(env, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})

    response = client.post("/signout", headers=_get_csrf_headers(client))

    assert response.status_code == 200
    assert response.json()["redirect"] == "/"


# ---------------------------------------------------------------------------
# /api/status
# ---------------------------------------------------------------------------


def test_status_returns_200_with_correct_shape(client: TestClient, test_app: FastAPI) -> None:
    test_app.dependency_overrides[get_occupancy_service] = lambda: _mock_occupancy_svc()
    test_app.dependency_overrides[get_presence_service] = lambda: _mock_presence_svc()
    test_app.dependency_overrides[get_message_service] = lambda: _mock_message_svc()
    test_app.dependency_overrides[get_weather_service] = lambda: None

    response = client.get("/api/status")

    assert response.status_code == 200
    body = response.json()
    assert "occupancy" in body
    assert "presence" in body
    assert body["presence"]["level"] == PresenceLevel.EMPTY
    assert body["presence"]["message"] == "Niemand da"
    assert body["occupancy"]["type"] == OccupancyType.NONE


def test_status_works_with_few_presence_level(client: TestClient, test_app: FastAPI) -> None:
    test_app.dependency_overrides[get_occupancy_service] = lambda: _mock_occupancy_svc()
    test_app.dependency_overrides[get_presence_service] = lambda: _mock_presence_svc(PresenceLevel.FEW)
    test_app.dependency_overrides[get_message_service] = lambda: _mock_message_svc("Ein paar Leute")
    test_app.dependency_overrides[get_weather_service] = lambda: None

    response = client.get("/api/status")

    assert response.status_code == 200
    assert response.json()["presence"]["level"] == PresenceLevel.FEW


def test_status_for_date_query_param_forwarded(client: TestClient, test_app: FastAPI) -> None:
    occ_svc = _mock_occupancy_svc()
    test_app.dependency_overrides[get_occupancy_service] = lambda: occ_svc
    test_app.dependency_overrides[get_presence_service] = lambda: _mock_presence_svc()
    test_app.dependency_overrides[get_message_service] = lambda: _mock_message_svc()
    test_app.dependency_overrides[get_weather_service] = lambda: None

    client.get("/api/status?for_date=2026-04-12")

    occ_svc.get_occupancy.assert_called_once_with("2026-04-12")


def test_status_includes_last_error_when_present(client: TestClient, test_app: FastAPI) -> None:
    presence_svc = _mock_presence_svc()
    presence_svc.get_last_error.return_value = RuntimeError("router unreachable")
    test_app.dependency_overrides[get_occupancy_service] = lambda: _mock_occupancy_svc()
    test_app.dependency_overrides[get_presence_service] = lambda: presence_svc
    test_app.dependency_overrides[get_message_service] = lambda: _mock_message_svc()
    test_app.dependency_overrides[get_weather_service] = lambda: None

    body = client.get("/api/status").json()

    assert body["presence"]["last_error"] == "router unreachable"


# ---------------------------------------------------------------------------
# /api/push
# ---------------------------------------------------------------------------


def test_push_vapid_key_returns_200(client: TestClient, test_app: FastAPI) -> None:
    push_svc = MagicMock()
    push_svc.get_public_key.return_value = "test-vapid-public-key"
    test_app.dependency_overrides[get_push_subscription_service] = lambda: push_svc

    response = client.get("/api/push/vapid-key")

    assert response.status_code == 200
    assert response.json()["public_key"] == "test-vapid-public-key"


def test_push_all_endpoints_return_503_when_not_configured(client: TestClient, test_app: FastAPI) -> None:
    from fastapi import HTTPException

    def _raise_503() -> None:
        raise HTTPException(status_code=503, detail="Push notifications not configured")

    test_app.dependency_overrides[get_push_subscription_service] = _raise_503
    assert client.get("/api/push/vapid-key").status_code == 503
    assert client.post("/api/push/status", json={"auth": "x"}).status_code == 503
    assert client.post("/api/push/subscribe", json={"endpoint": "x", "p256dh": "x", "auth": "x"}).status_code == 503
    assert client.request("DELETE", "/api/push/unsubscribe", json={"auth": "x"}).status_code == 503


def test_push_status_returns_subscribed_false(
    client: TestClient, test_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    push_svc = MagicMock()
    push_svc.has.return_value = False
    test_app.dependency_overrides[get_push_subscription_service] = lambda: push_svc

    from app.services.PushSubscriptionService import PushSubscriptionService

    monkeypatch.setattr(PushSubscriptionService, "validate_auth", staticmethod(lambda _: None))  # type: ignore[reportUnknownLambdaType]

    response = client.post("/api/push/status", json={"auth": "dummyauth"})

    assert response.status_code == 200
    assert response.json()["subscribed"] is False


def test_push_unsubscribe_returns_404_when_not_found(client: TestClient, test_app: FastAPI) -> None:
    push_svc = MagicMock()
    push_svc.remove.return_value = False
    test_app.dependency_overrides[get_push_subscription_service] = lambda: push_svc

    response = client.request("DELETE", "/api/push/unsubscribe", json={"auth": "dummyauth"})

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# /api/internal/details
# ---------------------------------------------------------------------------


def test_internal_details_returns_401_without_auth(client: TestClient, test_app: FastAPI) -> None:
    test_app.dependency_overrides[get_internal_service] = lambda: _mock_internal_svc()

    response = client.get("/api/internal/details")

    assert response.status_code == 401


def test_internal_details_returns_200_with_admin_auth(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(env, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    test_app.dependency_overrides[get_internal_service] = lambda: _mock_internal_svc()

    response = client.get("/api/internal/details", headers={"api_key": TEST_ADMIN_TOKEN})

    assert response.status_code == 200
    body = response.json()
    assert body["active_devices"] == 0
    assert body["wardens_on_site"] == []
    assert body["last_error"] is None


def test_internal_details_surfaces_active_device_count(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(env, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    svc = _mock_internal_svc()
    svc.get_active_devices_ct.return_value = 5
    warden = MagicMock()
    warden.name = "Alice"
    svc.get_wardens_on_site.return_value = [warden]
    test_app.dependency_overrides[get_internal_service] = lambda: svc

    body = client.get("/api/internal/details", headers={"api_key": TEST_ADMIN_TOKEN}).json()

    assert body["active_devices"] == 5
    assert body["wardens_on_site"] == ["Alice"]


def test_admin_session_invalidated_after_token_rotation(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After ADMIN_TOKEN is rotated, an existing admin session must be rejected."""
    monkeypatch.setattr(env, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    test_app.dependency_overrides[get_internal_service] = lambda: _mock_internal_svc()

    # Establish an admin session with the original token
    response = client.get("/api/internal/details", headers={"api_key": TEST_ADMIN_TOKEN})
    assert response.status_code == 200

    # Rotate the token - subsequent session-only requests must now be rejected
    monkeypatch.setattr(env, "ADMIN_TOKEN", "rotated-" + TEST_ADMIN_TOKEN)

    response = client.get("/api/internal/details")
    assert response.status_code == 401


def test_header_auth_regenerates_session_id(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Session ID must change when transitioning unauthenticated → authenticated via API key header."""
    monkeypatch.setattr(env, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    test_app.dependency_overrides[get_internal_service] = lambda: _mock_internal_svc()

    # Sign in and immediately sign out to get an existing session cookie in unauthenticated state
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})
    session_id_before = _get_session_cookie_value(client)
    client.post("/signout", headers=_get_csrf_headers(client))

    # Authenticate via header — session ID must be regenerated
    response = client.get("/api/internal/details", headers={"api_key": TEST_ADMIN_TOKEN})
    assert response.status_code == 200
    session_id_after = _get_session_cookie_value(client)

    assert session_id_before != session_id_after


# ---------------------------------------------------------------------------
# /api/notifications
# ---------------------------------------------------------------------------


def test_notifications_list_returns_401_without_auth(client: TestClient, test_app: FastAPI) -> None:
    test_app.dependency_overrides[get_notification_service] = lambda: _mock_notification_svc()

    response = client.get("/api/notifications/list")

    assert response.status_code == 401


def test_notifications_list_returns_empty_list_with_auth(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(env, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    svc = _mock_notification_svc()
    svc.list_all.return_value = []
    test_app.dependency_overrides[get_notification_service] = lambda: svc

    response = client.get("/api/notifications/list", headers={"api_key": TEST_ADMIN_TOKEN})

    assert response.status_code == 200
    assert response.json() == []


def test_notifications_html_returns_empty_string_for_no_results(client: TestClient, test_app: FastAPI) -> None:
    svc = _mock_notification_svc()
    svc.get.return_value = []
    test_app.dependency_overrides[get_notification_service] = lambda: svc

    response = client.get("/api/notifications?n_ids=all_active")

    assert response.status_code == 200
    assert response.text == ""


def test_notifications_html_renders_markdown(client: TestClient, test_app: FastAPI) -> None:
    notif = Notification(
        id="nid-abc123",
        message="Hello **world**",
        created=_NOW,
        valid_from=None,
        valid_until=None,
        enabled=True,
    )
    svc = _mock_notification_svc()
    svc.get.return_value = [notif]
    test_app.dependency_overrides[get_notification_service] = lambda: svc

    response = client.get("/api/notifications?n_ids=all_active")

    assert response.status_code == 200
    assert 'data-notification-id="nid-abc123"' in response.text
    assert "<strong>world</strong>" in response.text


def test_notifications_post_returns_401_without_auth(client: TestClient, test_app: FastAPI) -> None:
    test_app.dependency_overrides[get_notification_service] = lambda: _mock_notification_svc()

    response = client.post("/api/notifications", json={"message": "test"})

    assert response.status_code == 401


def test_notifications_post_rejects_missing_csrf_for_session_auth(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(env, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    svc = _mock_notification_svc()
    test_app.dependency_overrides[get_notification_service] = lambda: svc
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})

    response = client.post("/api/notifications", json={"message": "Test message"})

    assert response.status_code == 403
    svc.add.assert_not_called()


def test_notifications_post_accepts_valid_csrf_for_session_auth(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(env, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    svc = _mock_notification_svc()
    svc.add.return_value = "nid-session123"
    test_app.dependency_overrides[get_notification_service] = lambda: svc
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})

    response = client.post(
        "/api/notifications",
        json={"message": "Test message"},
        headers=_get_csrf_headers(client),
    )

    assert response.status_code == 200
    assert response.json()["notification_id"] == "nid-session123"


def test_notifications_post_returns_notification_id(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(env, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    svc = _mock_notification_svc()
    svc.add.return_value = "nid-new123"
    test_app.dependency_overrides[get_notification_service] = lambda: svc

    response = client.post(
        "/api/notifications",
        json={"message": "Test message"},
        headers={"api_key": TEST_ADMIN_TOKEN},
    )

    assert response.status_code == 200
    assert response.json()["notification_id"] == "nid-new123"


def test_notifications_delete_returns_404_when_not_found(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(env, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    svc = _mock_notification_svc()
    svc.delete.return_value = False
    test_app.dependency_overrides[get_notification_service] = lambda: svc

    response = client.request("DELETE", "/api/notifications/nid-missing", headers={"api_key": TEST_ADMIN_TOKEN})

    assert response.status_code == 404


def test_notifications_delete_returns_200_when_found(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(env, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    svc = _mock_notification_svc()
    svc.delete.return_value = True
    test_app.dependency_overrides[get_notification_service] = lambda: svc

    response = client.request("DELETE", "/api/notifications/nid-abc123", headers={"api_key": TEST_ADMIN_TOKEN})

    assert response.status_code == 200
