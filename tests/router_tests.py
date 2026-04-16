"""HTTP-level tests for all routers.

Each test overrides exactly the service getters it needs via
``test_app.dependency_overrides`` (set up by the function-scoped ``client``
fixture in conftest.py).  The TestClient resolves dependencies through
FastAPI's normal DI machinery, so no monkey-patching of globals is required.

Auth-protected endpoints are exercised with a fixed admin token injected via
``monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)`` and sent as
the ``api_key`` request header.
"""

from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.access_role import AccessRole
from app.api.ephemeral_api_key_store import EphemeralAPIKeyStore
from app.api.responses import ApiKey
from app.config import cfg
from app.dependencies import (
    get_internal_service,
    get_message_service,
    get_notification_service,
    get_occupancy_service,
    get_presence_service,
    get_push_subscription_service,
    get_weather_service,
)
from app.services.internal.warden_store import WardenStore
from app.services.message_service import StatusMessage
from app.services.notification_service import Notification
from app.services.occupancy.model import DailyOccupancy, OccupancySource, OccupancyType
from app.services.presence_level import PresenceLevel
from app.services.push_subscription_service import PushSubscriptionService
from tests.conftest import TEST_ADMIN_TOKEN, mock_internal_svc

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
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)

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
    monkeypatch.setattr(cfg, "API_KEYS_PATH", str(keys_path))
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
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)

    response = client.post("/auth", json={"token": "wrong-token", "next": "/"})

    assert response.status_code == 401


def test_post_auth_admin_token_grants_api_access(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Logging in via the form with ADMIN_TOKEN should allow access to protected API endpoints."""
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    test_app.dependency_overrides[get_internal_service] = mock_internal_svc

    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})

    response = client.get("/api/internal/details")
    assert response.status_code == 200


def test_get_auth_page_renders_password_field(client: TestClient) -> None:
    response = client.get("/auth")

    assert response.status_code == 200
    assert 'id="auth-form"' in response.text
    assert 'type="password"' in response.text


# ---------------------------------------------------------------------------
# Setup banner
# ---------------------------------------------------------------------------


def test_index_shows_setup_banner_when_no_admin_token(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Setup banner must be visible (no 'hidden' class) when no ADMIN_TOKEN is set."""
    monkeypatch.setattr(cfg, "API_KEYS_PATH", str(tmp_path / "api_keys.json"))
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", "")
    EphemeralAPIKeyStore.save([])

    response = client.get("/")

    assert response.status_code == 200
    assert 'id="bootstrap-banner"' in response.text
    assert "bootstrap-banner hidden" not in response.text
    assert "ADMIN_TOKEN" in response.text


def test_index_hides_setup_banner_when_admin_token_set(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Setup banner must have the 'hidden' class when ADMIN_TOKEN is configured."""
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)

    response = client.get("/")

    assert response.status_code == 200
    assert "bootstrap-banner hidden" in response.text


# ---------------------------------------------------------------------------
# Floating button group — visible class
# ---------------------------------------------------------------------------


def test_index_floating_btn_group_is_visible_when_signin_btn_shown(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """floating-btn-group must carry class="visible" when the sign-in button is rendered."""
    monkeypatch.setattr(cfg.features, "is_login_button_enabled", lambda: True)

    response = client.get("/")

    assert response.status_code == 200
    assert 'id="floating-btn-group" class="visible"' in response.text


def test_index_floating_btn_group_not_visible_without_any_buttons(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When no auth / action buttons are shown, the group must not carry class="visible"."""
    monkeypatch.setattr(cfg.features, "is_login_button_enabled", lambda: False)

    response = client.get("/")

    assert response.status_code == 200
    assert 'id="floating-btn-group" class="visible"' not in response.text


# ---------------------------------------------------------------------------
# Floating button group — signin / signout visibility
# ---------------------------------------------------------------------------


def test_index_shows_signin_btn_when_not_signed_in(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg.features, "is_login_button_enabled", lambda: True)

    response = client.get("/")

    assert response.status_code == 200
    assert 'id="signin-btn"' in response.text
    assert 'id="signout-btn"' not in response.text


def test_index_shows_signout_btn_when_signed_in(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    monkeypatch.setattr(cfg.features, "is_login_button_enabled", lambda: True)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})

    response = client.get("/")

    assert response.status_code == 200
    assert 'id="signin-btn"' not in response.text
    assert 'id="signout-btn"' in response.text


def test_index_hides_signin_btn_when_login_button_disabled(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg.features, "is_login_button_enabled", lambda: False)

    response = client.get("/")

    assert response.status_code == 200
    assert 'id="signin-btn"' not in response.text


def test_auth_page_never_shows_signin_btn(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """The auth form IS the sign-in UI; the floating signin button must not render."""
    monkeypatch.setattr(cfg.features, "is_login_button_enabled", lambda: True)

    response = client.get("/auth")

    assert response.status_code == 200
    assert 'id="signin-btn"' not in response.text


def test_auth_page_shows_no_floating_signout_btn_when_signed_in(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Auth page has its own inline signed-in panel; no floating signout button needed."""
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})

    response = client.get("/auth")

    assert response.status_code == 200
    assert 'id="signout-btn"' not in response.text


def test_legal_page_shows_no_floating_auth_btns(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Legal page has show_auth_button=False — no floating signin or signout buttons."""
    monkeypatch.setattr(cfg, "OPERATOR_NAME", "Max Mustermann")
    monkeypatch.setattr(cfg, "OPERATOR_EMAIL", "max@example.com")
    monkeypatch.setattr(cfg.features, "is_login_button_enabled", lambda: True)
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})

    response = client.get("/legal")

    assert response.status_code == 200
    assert 'id="signin-btn"' not in response.text
    assert 'id="signout-btn"' not in response.text


def test_legal_page_always_shows_back_button(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Any sub-page (not /) shows a back button that uses browser history."""
    monkeypatch.setattr(cfg, "OPERATOR_NAME", "Max Mustermann")
    monkeypatch.setattr(cfg, "OPERATOR_EMAIL", "max@example.com")

    response = client.get("/legal")

    assert response.status_code == 200
    assert 'title="Zurück"' in response.text
    assert "history.back()" in response.text


def test_index_has_no_back_button(client: TestClient) -> None:
    """The index page ('/') must not show a back button."""
    response = client.get("/")

    assert response.status_code == 200
    assert 'title="Zurück"' not in response.text


def test_notification_create_page_shows_preview_not_create_btn(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})

    response = client.get("/notification-create")

    assert response.status_code == 200
    assert 'id="signout-btn"' not in response.text
    # Already on notification-create — no circular button
    assert 'href="/notification-create"' not in response.text
    # Preview button should be visible
    assert 'href="/preview/notifications' in response.text


def test_index_shows_notification_btns_for_operator_role(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """when_role(NOTIFICATION_OPERATOR) predicate reveals buttons for operator-role session."""
    keys_path = tmp_path / "api_keys.json"
    monkeypatch.setattr(cfg, "API_KEYS_PATH", str(keys_path))
    api_key = ApiKey.generate_new(
        comment="test-operator",
        valid_until=datetime(2030, 12, 31, tzinfo=_UTC),
        role=AccessRole.NOTIFICATION_OPERATOR,
    )
    assert EphemeralAPIKeyStore.append(api_key)
    client.post("/auth", json={"token": api_key.key, "next": "/"})

    response = client.get("/")

    assert response.status_code == 200
    assert 'href="/notification-create"' in response.text
    assert 'href="/preview/notifications' in response.text


def test_index_hides_notification_btns_when_not_signed_in(client: TestClient) -> None:
    """Notification buttons must not appear for unauthenticated visitors on the index page."""
    response = client.get("/")

    assert response.status_code == 200
    assert 'href="/notification-create"' not in response.text
    assert 'href="/preview/notifications' not in response.text


def test_index_hides_notification_btns_for_reader_role(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """READER role is below NOTIFICATION_OPERATOR — buttons must stay hidden."""
    keys_path = tmp_path / "api_keys.json"
    monkeypatch.setattr(cfg, "API_KEYS_PATH", str(keys_path))
    api_key = ApiKey.generate_new(
        comment="test-reader",
        valid_until=datetime(2030, 12, 31, tzinfo=_UTC),
        role=AccessRole.READER,
    )
    assert EphemeralAPIKeyStore.append(api_key)
    client.post("/auth", json={"token": api_key.key, "next": "/"})

    response = client.get("/")

    assert response.status_code == 200
    assert 'href="/notification-create"' not in response.text
    assert 'href="/preview/notifications' not in response.text


def test_get_legal_page_renders_impressum(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "OPERATOR_NAME", "Max Mustermann")
    monkeypatch.setattr(cfg, "OPERATOR_EMAIL", "max@example.com")

    response = client.get("/legal")

    assert response.status_code == 200
    assert "Impressum" in response.text
    assert "Datenschutzerklärung" in response.text
    assert "Max Mustermann" in response.text
    assert "max@example.com" in response.text


def test_get_legal_page_returns_404_when_operator_not_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cfg, "OPERATOR_NAME", "")
    monkeypatch.setattr(cfg, "OPERATOR_EMAIL", "")

    response = client.get("/legal")

    assert response.status_code == 404


def test_get_legal_page_returns_404_when_only_name_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cfg, "OPERATOR_NAME", "Max Mustermann")
    monkeypatch.setattr(cfg, "OPERATOR_EMAIL", "")

    response = client.get("/legal")

    assert response.status_code == 404


def test_get_legal_page_shows_push_section_when_feature_enabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cfg, "OPERATOR_NAME", "Max Mustermann")
    monkeypatch.setattr(cfg, "OPERATOR_EMAIL", "max@example.com")
    monkeypatch.setattr(cfg.features, "is_push_enabled", lambda: True)
    monkeypatch.setattr(cfg.features, "is_presence_enabled", lambda: False)
    monkeypatch.setattr(cfg.features, "is_weather_enabled", lambda: False)

    response = client.get("/legal")

    assert response.status_code == 200
    assert "Push-Benachrichtigungen" in response.text
    assert "WLAN-Anwesenheitserkennung" not in response.text
    assert "OpenWeatherMap" not in response.text


@pytest.mark.parametrize(
    ("push", "presence", "weather", "expected_in", "expected_not_in"),
    [
        (False, False, False, [], ["Push-Benachrichtigungen", "WLAN-Anwesenheitserkennung", "OpenWeatherMap"]),
        (False, True, False, ["WLAN-Anwesenheitserkennung", "Namentliche Zuordnung"], ["OpenWeatherMap"]),
        (False, False, True, ["OpenWeatherMap"], ["WLAN-Anwesenheitserkennung"]),
    ],
    ids=["all-disabled", "presence-only", "weather-only"],
)
def test_get_legal_page_feature_sections(  # noqa: PLR0913
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    push: bool,  # noqa: FBT001
    presence: bool,  # noqa: FBT001
    weather: bool,  # noqa: FBT001
    expected_in: list[str],
    expected_not_in: list[str],
) -> None:
    monkeypatch.setattr(cfg, "OPERATOR_NAME", "Max Mustermann")
    monkeypatch.setattr(cfg, "OPERATOR_EMAIL", "max@example.com")
    monkeypatch.setattr(cfg.features, "is_push_enabled", lambda: push)
    monkeypatch.setattr(cfg.features, "is_presence_enabled", lambda: presence)
    monkeypatch.setattr(cfg.features, "is_weather_enabled", lambda: weather)

    response = client.get("/legal")

    assert response.status_code == 200
    for text in expected_in:
        assert text in response.text
    for text in expected_not_in:
        assert text not in response.text


def test_index_shows_legal_link_when_operator_configured(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "OPERATOR_NAME", "Max Mustermann")
    monkeypatch.setattr(cfg, "OPERATOR_EMAIL", "max@example.com")

    response = client.get("/")

    assert response.status_code == 200
    assert 'href="/legal"' in response.text


def test_index_hides_legal_link_when_operator_not_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cfg, "OPERATOR_NAME", "")
    monkeypatch.setattr(cfg, "OPERATOR_EMAIL", "")

    response = client.get("/")

    assert response.status_code == 200
    assert 'href="/legal"' not in response.text


def test_get_auth_page_includes_csrf_cookie_when_signed_in(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})

    response = client.get("/auth")

    assert response.status_code == 200
    assert client.cookies.get("csrftoken") is not None


def test_signout_rejects_missing_csrf_for_session_auth(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})

    response = client.post("/signout")

    assert response.status_code == 403


def test_signout_accepts_valid_csrf_for_session_auth(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})

    response = client.post("/signout", headers=_get_csrf_headers(client), follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_signout_accepts_valid_csrf_form_field(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FormFieldCSRFMiddleware must also accept the token from a hidden form field."""
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})
    csrf_token = client.cookies.get("csrftoken")
    assert csrf_token is not None

    response = client.post(
        "/signout",
        data={"x-csrf-token": csrf_token},
        headers={"content-type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_signout_clears_session_and_csrf_cookies(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})

    response = client.post("/signout", headers=_get_csrf_headers(client), follow_redirects=False)

    assert response.status_code == 303
    set_cookie_headers = response.headers.get_list("set-cookie")
    # session_cookie must be expired
    session_cookies = [h for h in set_cookie_headers if "session_cookie=" in h]
    assert any("expires=Thu, 01 Jan 1970" in c or "max-age=0" in c.lower() for c in session_cookies), (
        "session_cookie was not expired in signout response"
    )
    # csrftoken must be expired
    csrf_cookies = [h for h in set_cookie_headers if "csrftoken=" in h]
    assert any("max-age=0" in c.lower() for c in csrf_cookies), "csrftoken was not expired in signout response"


# ---------------------------------------------------------------------------
# /manifest.json (PWA manifest)
# ---------------------------------------------------------------------------


def test_manifest_json_returns_valid_pwa_manifest(client: TestClient) -> None:
    response = client.get("/manifest.json")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/manifest+json"
    body = response.json()
    assert body["display"] == "standalone"
    assert body["start_url"] == "/"
    assert body["name"] == "Fribbe Beach - Status"
    assert len(body["icons"]) > 0


def test_index_html_includes_pwa_meta_tags(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert '<link rel="manifest" href="/manifest.json">' in html
    assert "mobile-web-app-capable" in html
    assert "apple-touch-icon" in html


def test_index_html_includes_ios_install_hint(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert 'id="push-ios-hint"' in response.text


# ---------------------------------------------------------------------------
# /api/status
# ---------------------------------------------------------------------------


def test_status_returns_200_with_correct_shape(client: TestClient, test_app: FastAPI) -> None:
    test_app.dependency_overrides[get_occupancy_service] = _mock_occupancy_svc
    test_app.dependency_overrides[get_presence_service] = _mock_presence_svc
    test_app.dependency_overrides[get_message_service] = _mock_message_svc
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
    test_app.dependency_overrides[get_occupancy_service] = _mock_occupancy_svc
    test_app.dependency_overrides[get_presence_service] = lambda: _mock_presence_svc(PresenceLevel.FEW)
    test_app.dependency_overrides[get_message_service] = lambda: _mock_message_svc("Ein paar Leute")
    test_app.dependency_overrides[get_weather_service] = lambda: None

    response = client.get("/api/status")

    assert response.status_code == 200
    assert response.json()["presence"]["level"] == PresenceLevel.FEW


def test_status_for_date_query_param_forwarded(client: TestClient, test_app: FastAPI) -> None:
    occ_svc = _mock_occupancy_svc()
    test_app.dependency_overrides[get_occupancy_service] = lambda: occ_svc
    test_app.dependency_overrides[get_presence_service] = _mock_presence_svc
    test_app.dependency_overrides[get_message_service] = _mock_message_svc
    test_app.dependency_overrides[get_weather_service] = lambda: None

    client.get("/api/status?for_date=2026-04-12")

    occ_svc.get_occupancy.assert_called_once_with("2026-04-12")


def test_status_includes_last_error_when_present(client: TestClient, test_app: FastAPI) -> None:
    presence_svc = _mock_presence_svc()
    presence_svc.get_last_error.return_value = RuntimeError("router unreachable")
    test_app.dependency_overrides[get_occupancy_service] = _mock_occupancy_svc
    test_app.dependency_overrides[get_presence_service] = lambda: presence_svc
    test_app.dependency_overrides[get_message_service] = _mock_message_svc
    test_app.dependency_overrides[get_weather_service] = lambda: None

    body = client.get("/api/status").json()

    assert body["presence"]["last_error"] == "router unreachable"


# ---------------------------------------------------------------------------
# /status/content
# ---------------------------------------------------------------------------


def test_status_content_returns_200_with_html(client: TestClient, test_app: FastAPI) -> None:
    test_app.dependency_overrides[get_occupancy_service] = _mock_occupancy_svc
    test_app.dependency_overrides[get_presence_service] = _mock_presence_svc
    test_app.dependency_overrides[get_message_service] = _mock_message_svc
    test_app.dependency_overrides[get_weather_service] = lambda: None

    response = client.get("/status/content")

    assert response.status_code == 200
    assert 'data-level="empty"' in response.text
    assert "Niemand da" in response.text


def test_status_content_renders_few_level(client: TestClient, test_app: FastAPI) -> None:
    test_app.dependency_overrides[get_occupancy_service] = _mock_occupancy_svc
    test_app.dependency_overrides[get_presence_service] = lambda: _mock_presence_svc(PresenceLevel.FEW)
    test_app.dependency_overrides[get_message_service] = lambda: _mock_message_svc("Ein paar Leute")
    test_app.dependency_overrides[get_weather_service] = lambda: None

    response = client.get("/status/content")

    assert response.status_code == 200
    assert 'data-level="few"' in response.text
    assert "Ein paar Leute" in response.text


def test_status_content_for_date_forwarded(client: TestClient, test_app: FastAPI) -> None:
    occ_svc = _mock_occupancy_svc()
    test_app.dependency_overrides[get_occupancy_service] = lambda: occ_svc
    test_app.dependency_overrides[get_presence_service] = _mock_presence_svc
    test_app.dependency_overrides[get_message_service] = _mock_message_svc
    test_app.dependency_overrides[get_weather_service] = lambda: None

    client.get("/status/content?for_date=2026-04-12")

    occ_svc.get_occupancy.assert_called_once_with("2026-04-12")


def test_status_content_renders_occupancy_fully(client: TestClient, test_app: FastAPI) -> None:
    test_app.dependency_overrides[get_occupancy_service] = lambda: _mock_occupancy_svc(OccupancyType.FULLY)
    test_app.dependency_overrides[get_presence_service] = _mock_presence_svc
    test_app.dependency_overrides[get_message_service] = _mock_message_svc
    test_app.dependency_overrides[get_weather_service] = lambda: None

    response = client.get("/status/content")

    assert response.status_code == 200
    assert "occupancy-fully" in response.text


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

    def _raise_503() -> None:
        raise HTTPException(status_code=503, detail="Push notifications not configured")

    test_app.dependency_overrides[get_push_subscription_service] = _raise_503
    assert client.get("/api/push/vapid-key").status_code == 503
    assert client.post("/api/push/status", json={"auth": "x"}).status_code == 503
    assert client.post("/api/push/subscribe", json={"endpoint": "x", "p256dh": "x", "auth": "x"}).status_code == 503
    assert client.request("DELETE", "/api/push/unsubscribe", json={"auth": "x"}).status_code == 503


def test_push_status_returns_subscribed_false(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    push_svc = MagicMock()
    push_svc.has.return_value = False
    test_app.dependency_overrides[get_push_subscription_service] = lambda: push_svc

    monkeypatch.setattr(PushSubscriptionService, "validate_auth", staticmethod(lambda _: None))  # type: ignore[reportUnknownLambdaType]

    response = client.post("/api/push/status", json={"auth": "dummyauth"})

    assert response.status_code == 200
    body = response.json()
    assert body["subscribed"] is False
    assert body["topics"] == []


def test_push_status_returns_topics_when_subscribed(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    push_svc = MagicMock()
    push_svc.has.return_value = True
    push_svc.get_topics.return_value = ["presence"]
    test_app.dependency_overrides[get_push_subscription_service] = lambda: push_svc

    monkeypatch.setattr(PushSubscriptionService, "validate_auth", staticmethod(lambda _: None))  # type: ignore[reportUnknownLambdaType]

    response = client.post("/api/push/status", json={"auth": "dummyauth"})

    assert response.status_code == 200
    body = response.json()
    assert body["subscribed"] is True
    assert body["topics"] == ["presence"]


def test_push_topics_patch_returns_200(client: TestClient, test_app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    push_svc = MagicMock()
    push_svc.update_topics.return_value = True
    test_app.dependency_overrides[get_push_subscription_service] = lambda: push_svc

    monkeypatch.setattr(PushSubscriptionService, "validate_auth", staticmethod(lambda _: None))  # type: ignore[reportUnknownLambdaType]

    response = client.patch("/api/push/topics", json={"auth": "dummyauth", "topics": ["presence"]})

    assert response.status_code == 200
    push_svc.update_topics.assert_called_once_with("dummyauth", ["presence"])


def test_push_topics_patch_returns_404_when_not_found(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    push_svc = MagicMock()
    push_svc.update_topics.return_value = False
    test_app.dependency_overrides[get_push_subscription_service] = lambda: push_svc

    monkeypatch.setattr(PushSubscriptionService, "validate_auth", staticmethod(lambda _: None))  # type: ignore[reportUnknownLambdaType]

    response = client.patch("/api/push/topics", json={"auth": "dummyauth", "topics": ["notifications"]})

    assert response.status_code == 404


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
    test_app.dependency_overrides[get_internal_service] = mock_internal_svc

    response = client.get("/api/internal/details")

    assert response.status_code == 401


def test_internal_details_returns_200_with_admin_auth(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    test_app.dependency_overrides[get_internal_service] = mock_internal_svc

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
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    svc = mock_internal_svc()
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
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    test_app.dependency_overrides[get_internal_service] = mock_internal_svc

    # Establish an admin session with the original token
    response = client.get("/api/internal/details", headers={"api_key": TEST_ADMIN_TOKEN})
    assert response.status_code == 200

    # Rotate the token - subsequent session-only requests must now be rejected
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", "rotated-" + TEST_ADMIN_TOKEN)

    response = client.get("/api/internal/details")
    assert response.status_code == 401


def test_header_auth_regenerates_session_id(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Session ID must change when transitioning unauthenticated → authenticated via API key header."""
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    test_app.dependency_overrides[get_internal_service] = mock_internal_svc

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
    test_app.dependency_overrides[get_notification_service] = _mock_notification_svc

    response = client.get("/api/notifications/list")

    assert response.status_code == 401


def test_notifications_list_returns_empty_list_with_auth(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
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


def test_notification_content_returns_empty_for_no_results(client: TestClient, test_app: FastAPI) -> None:
    svc = _mock_notification_svc()
    svc.get.return_value = []
    test_app.dependency_overrides[get_notification_service] = lambda: svc

    response = client.get("/notifications/content?n_ids=all_active")

    assert response.status_code == 200
    assert response.text == ""


def test_notification_content_renders_markdown(client: TestClient, test_app: FastAPI) -> None:
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

    response = client.get("/notifications/content?n_ids=all_active")

    assert response.status_code == 200
    assert 'data-notification-id="nid-abc123"' in response.text
    assert "<strong>world</strong>" in response.text


def test_notifications_post_returns_401_without_auth(client: TestClient, test_app: FastAPI) -> None:
    test_app.dependency_overrides[get_notification_service] = _mock_notification_svc

    response = client.post("/api/notifications", json={"message": "test"})

    assert response.status_code == 401


def test_notifications_post_rejects_missing_csrf_for_session_auth(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
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
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
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
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
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
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
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
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    svc = _mock_notification_svc()
    svc.delete.return_value = True
    test_app.dependency_overrides[get_notification_service] = lambda: svc

    response = client.request("DELETE", "/api/notifications/nid-abc123", headers={"api_key": TEST_ADMIN_TOKEN})

    assert response.status_code == 200


def test_notifications_put_returns_404_when_not_found(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    svc = _mock_notification_svc()
    svc.update.return_value = False
    test_app.dependency_overrides[get_notification_service] = lambda: svc

    response = client.put(
        "/api/notifications/nid-missing",
        json={"enabled": True},
        headers={"api_key": TEST_ADMIN_TOKEN},
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# /api-keys page
# ---------------------------------------------------------------------------


def test_api_keys_page_redirects_to_auth_when_not_signed_in(client: TestClient) -> None:
    """Unauthenticated access to /api-keys must redirect to /auth."""
    response = client.get("/api-keys", follow_redirects=False)

    assert response.status_code == 302
    assert "/auth" in response.headers["location"]


def test_api_keys_page_returns_403_for_reader_role(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """READER role is below ADMIN — /api-keys must return 403."""
    keys_path = tmp_path / "api_keys.json"
    monkeypatch.setattr(cfg, "API_KEYS_PATH", str(keys_path))
    api_key = ApiKey.generate_new(
        comment="test-reader",
        valid_until=datetime(2030, 12, 31, tzinfo=_UTC),
        role=AccessRole.READER,
    )
    assert EphemeralAPIKeyStore.append(api_key)
    client.post("/auth", json={"token": api_key.key, "next": "/"})

    response = client.get("/api-keys")

    assert response.status_code == 403


def test_api_keys_page_returns_403_for_operator_role(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """NOTIFICATION_OPERATOR role is below ADMIN — /api-keys must return 403."""
    keys_path = tmp_path / "api_keys.json"
    monkeypatch.setattr(cfg, "API_KEYS_PATH", str(keys_path))
    api_key = ApiKey.generate_new(
        comment="test-operator",
        valid_until=datetime(2030, 12, 31, tzinfo=_UTC),
        role=AccessRole.NOTIFICATION_OPERATOR,
    )
    assert EphemeralAPIKeyStore.append(api_key)
    client.post("/auth", json={"token": api_key.key, "next": "/"})

    response = client.get("/api-keys")

    assert response.status_code == 403


def test_api_keys_page_renders_for_admin(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADMIN role must be able to access /api-keys."""
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})

    response = client.get("/api-keys")

    assert response.status_code == 200
    assert "API-Schlüssel verwalten" in response.text
    assert 'id="create-key-form"' in response.text
    assert 'id="key-list-table"' in response.text
    assert f'value="{AccessRole.READER.value}"' in response.text  # role options populated from AccessRole
    assert "data-role-labels" in response.text


def test_index_shows_api_keys_btn_for_admin(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Admin users should see the API keys floating button on the index page."""
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    monkeypatch.setattr(cfg.features, "is_login_button_enabled", lambda: True)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})

    response = client.get("/")

    assert response.status_code == 200
    assert 'href="/api-keys"' in response.text


def test_index_hides_api_keys_btn_for_operator(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Operator-role users should not see the API keys button."""
    keys_path = tmp_path / "api_keys.json"
    monkeypatch.setattr(cfg, "API_KEYS_PATH", str(keys_path))
    api_key = ApiKey.generate_new(
        comment="test-operator",
        valid_until=datetime(2030, 12, 31, tzinfo=_UTC),
        role=AccessRole.NOTIFICATION_OPERATOR,
    )
    assert EphemeralAPIKeyStore.append(api_key)
    client.post("/auth", json={"token": api_key.key, "next": "/"})

    response = client.get("/")

    assert response.status_code == 200
    assert 'href="/api-keys"' not in response.text


def test_index_hides_api_keys_btn_when_not_signed_in(client: TestClient) -> None:
    """Unauthenticated visitors must not see the API keys button."""
    response = client.get("/")

    assert response.status_code == 200
    assert 'href="/api-keys"' not in response.text


def test_api_keys_page_has_back_button(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The /api-keys page is a sub-page and should show a back button."""
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})

    response = client.get("/api-keys")

    assert response.status_code == 200
    assert 'title="Zurück"' in response.text


# ---------------------------------------------------------------------------
# API key self-delete protection
# ---------------------------------------------------------------------------


def test_delete_own_api_key_returns_403(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An admin API key must not be allowed to delete itself."""
    keys_path = tmp_path / "api_keys.json"
    monkeypatch.setattr(cfg, "API_KEYS_PATH", str(keys_path))
    api_key = ApiKey.generate_new(
        comment="self-key",
        valid_until=datetime(2030, 12, 31, tzinfo=_UTC),
        role=AccessRole.ADMIN,
    )
    assert EphemeralAPIKeyStore.append(api_key)
    client.post("/auth", json={"token": api_key.key, "next": "/"})

    response = client.request(
        "DELETE",
        "/api/internal/api_key",
        json={"key": api_key.key[:5]},
        headers=_get_csrf_headers(client),
    )

    assert response.status_code == 403
    assert "own" in response.json()["detail"].lower()


def test_admin_token_can_delete_any_api_key(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """ADMIN_TOKEN users are not API keys themselves and can delete any key."""
    keys_path = tmp_path / "api_keys.json"
    monkeypatch.setattr(cfg, "API_KEYS_PATH", str(keys_path))
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    api_key = ApiKey.generate_new(
        comment="deletable",
        valid_until=datetime(2030, 12, 31, tzinfo=_UTC),
        role=AccessRole.ADMIN,
    )
    assert EphemeralAPIKeyStore.append(api_key)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})

    response = client.request(
        "DELETE",
        "/api/internal/api_key",
        json={"key": api_key.key[:5]},
        headers=_get_csrf_headers(client),
    )

    assert response.status_code == 200


def test_list_api_keys_includes_self_key_prefix(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The list endpoint must include self_key_prefix when authenticated with an API key."""
    keys_path = tmp_path / "api_keys.json"
    monkeypatch.setattr(cfg, "API_KEYS_PATH", str(keys_path))
    api_key = ApiKey.generate_new(
        comment="self-key",
        valid_until=datetime(2030, 12, 31, tzinfo=_UTC),
        role=AccessRole.ADMIN,
    )
    assert EphemeralAPIKeyStore.append(api_key)
    client.post("/auth", json={"token": api_key.key, "next": "/"})

    response = client.get("/api/internal/api_keys")

    assert response.status_code == 200
    body = response.json()
    assert body["self_key_prefix"] is not None
    assert body["self_key_prefix"] == api_key.key[:5] + "..."


def test_list_api_keys_has_null_self_key_prefix_for_admin_token(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """ADMIN_TOKEN sessions should have null self_key_prefix."""
    keys_path = tmp_path / "api_keys.json"
    monkeypatch.setattr(cfg, "API_KEYS_PATH", str(keys_path))
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    api_key = ApiKey.generate_new(
        comment="other-key",
        valid_until=datetime(2030, 12, 31, tzinfo=_UTC),
        role=AccessRole.ADMIN,
    )
    assert EphemeralAPIKeyStore.append(api_key)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})

    response = client.get("/api/internal/api_keys")

    assert response.status_code == 200
    body = response.json()
    assert body["self_key_prefix"] is None


# ---------------------------------------------------------------------------
# API key create validation
# ---------------------------------------------------------------------------


def test_create_api_key_rejects_empty_comment(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Creating a key without a comment must fail with 422."""
    keys_path = tmp_path / "api_keys.json"
    monkeypatch.setattr(cfg, "API_KEYS_PATH", str(keys_path))
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})

    response = client.post(
        "/api/internal/api_key",
        json={"comment": ""},
        headers=_get_csrf_headers(client),
    )

    assert response.status_code == 422


def test_create_api_key_rejects_oversized_comment(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Creating a key with a comment exceeding 200 characters must fail with 422."""
    keys_path = tmp_path / "api_keys.json"
    monkeypatch.setattr(cfg, "API_KEYS_PATH", str(keys_path))
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})

    response = client.post(
        "/api/internal/api_key",
        json={"comment": "x" * 201},
        headers=_get_csrf_headers(client),
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# /api/version, /api/version/content-hash, /api/licenses
# ---------------------------------------------------------------------------


def test_version_returns_build_version(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "BUILD_VERSION", "1.2.3")

    response = client.get("/api/version")

    assert response.status_code == 200
    assert response.json()["version"] == "1.2.3"


def test_version_content_hash_returns_hash(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "CONTENT_HASH_VERSION", "abc123")

    response = client.get("/api/version/content-hash")

    assert response.status_code == 200
    assert response.json()["version"] == "abc123"


def test_licenses_returns_list(client: TestClient) -> None:
    response = client.get("/api/licenses")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_favicon_returns_200(client: TestClient) -> None:
    response = client.get("/favicon.ico")

    assert response.status_code == 200


def test_service_worker_returns_js(client: TestClient) -> None:
    response = client.get("/sw.js")

    assert response.status_code == 200
    assert "application/javascript" in response.headers["content-type"]
    assert response.headers.get("service-worker-allowed") == "/"


def test_robots_txt_contains_disallows(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "APP_URL", "https://example.com")

    response = client.get("/robots.txt")

    assert response.status_code == 200
    assert "Disallow: /api/" in response.text
    assert "Sitemap: https://example.com/sitemap.xml" in response.text


def test_sitemap_xml_returns_valid_xml(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "APP_URL", "https://example.com")

    response = client.get("/sitemap.xml")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/xml"
    assert "<loc>https://example.com/</loc>" in response.text


# ---------------------------------------------------------------------------
# /api/internal/wardens — CRUD
# ---------------------------------------------------------------------------


def test_wardens_list_returns_200_with_auth(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    monkeypatch.setattr(cfg, "LOCAL_DATA_PATH", str(tmp_path))
    WardenStore._instance = None

    response = client.get("/api/internal/wardens", headers={"api_key": TEST_ADMIN_TOKEN})

    assert response.status_code == 200
    assert response.json()["wardens"] == []


def test_wardens_crud_lifecycle(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    monkeypatch.setattr(cfg, "LOCAL_DATA_PATH", str(tmp_path))
    WardenStore._instance = None
    auth = {"api_key": TEST_ADMIN_TOKEN}

    # Create (header-based auth — no CSRF needed)
    response = client.post(
        "/api/internal/wardens",
        json={"name": "Alice", "device_macs": ["AA:BB:CC:DD:EE:FF"], "device_names": ["Phone"]},
        headers=auth,
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Alice"

    # List
    client.cookies.clear()
    wardens = client.get("/api/internal/wardens", headers=auth).json()["wardens"]
    assert len(wardens) == 1

    # Update
    client.cookies.clear()
    response = client.put(
        "/api/internal/wardens/Alice",
        json={"device_names": ["Laptop"]},
        headers=auth,
    )
    assert response.status_code == 200
    assert response.json()["device_names"] == ["laptop"]

    # Delete
    client.cookies.clear()
    response = client.request("DELETE", "/api/internal/wardens/Alice", headers=auth)
    assert response.status_code == 204

    # Confirm deleted
    wardens = client.get("/api/internal/wardens", headers=auth).json()["wardens"]
    assert len(wardens) == 0


def test_wardens_create_duplicate_returns_409(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    monkeypatch.setattr(cfg, "LOCAL_DATA_PATH", str(tmp_path))
    WardenStore._instance = None
    auth = {"api_key": TEST_ADMIN_TOKEN}

    client.post(
        "/api/internal/wardens",
        json={"name": "Bob", "device_macs": ["AA:BB:CC:DD:EE:FF"], "device_names": ["Phone"]},
        headers=auth,
    )
    client.cookies.clear()
    response = client.post(
        "/api/internal/wardens",
        json={"name": "Bob", "device_macs": ["11:22:33:44:55:66"], "device_names": ["Tab"]},
        headers=auth,
    )

    assert response.status_code == 409


def test_wardens_update_not_found_returns_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    monkeypatch.setattr(cfg, "LOCAL_DATA_PATH", str(tmp_path))
    WardenStore._instance = None

    response = client.put(
        "/api/internal/wardens/NonExistent",
        json={"device_names": ["x"]},
        headers={"api_key": TEST_ADMIN_TOKEN},
    )

    assert response.status_code == 404


def test_wardens_delete_not_found_returns_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    monkeypatch.setattr(cfg, "LOCAL_DATA_PATH", str(tmp_path))
    WardenStore._instance = None

    response = client.request(
        "DELETE",
        "/api/internal/wardens/NonExistent",
        headers={"api_key": TEST_ADMIN_TOKEN},
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# /api/internal/config — threshold updates
# ---------------------------------------------------------------------------


def test_config_returns_204_when_no_thresholds_sent(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)

    response = client.patch("/api/internal/config", json={}, headers={"api_key": TEST_ADMIN_TOKEN})

    assert response.status_code == 204


def test_config_updates_min_non_empty_ct(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    monkeypatch.setattr(cfg, "LOCAL_DATA_PATH", str(tmp_path))

    response = client.patch(
        "/api/internal/config",
        json={"threshold_min_non_empty_ct": 5},
        headers={"api_key": TEST_ADMIN_TOKEN},
    )

    assert response.status_code == 200


def test_config_updates_min_many_ct(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    monkeypatch.setattr(cfg, "LOCAL_DATA_PATH", str(tmp_path))

    response = client.patch(
        "/api/internal/config",
        json={"threshold_min_many_ct": 15},
        headers={"api_key": TEST_ADMIN_TOKEN},
    )

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# /api/push — validation paths (422)
# ---------------------------------------------------------------------------


def test_push_status_returns_422_for_invalid_auth(client: TestClient, test_app: FastAPI) -> None:
    push_svc = MagicMock()
    test_app.dependency_overrides[get_push_subscription_service] = lambda: push_svc

    response = client.post("/api/push/status", json={"auth": ""})

    assert response.status_code == 422


def test_push_subscribe_returns_422_for_invalid_subscription(
    client: TestClient,
    test_app: FastAPI,
) -> None:
    push_svc = MagicMock()
    test_app.dependency_overrides[get_push_subscription_service] = lambda: push_svc

    response = client.post(
        "/api/push/subscribe",
        json={"endpoint": "", "p256dh": "", "auth": ""},
    )

    assert response.status_code == 422


def test_push_subscribe_returns_201_for_valid_subscription(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    push_svc = MagicMock()
    test_app.dependency_overrides[get_push_subscription_service] = lambda: push_svc
    monkeypatch.setattr(
        PushSubscriptionService,
        "validate_subscription",
        staticmethod(lambda *_a: None),  # type: ignore[reportUnknownLambdaType]
    )

    response = client.post(
        "/api/push/subscribe",
        json={"endpoint": "https://push.example.com", "p256dh": "key", "auth": "auth"},
    )

    assert response.status_code == 201
    push_svc.add.assert_called_once()


def test_push_topics_returns_422_for_invalid_auth(client: TestClient, test_app: FastAPI) -> None:
    push_svc = MagicMock()
    test_app.dependency_overrides[get_push_subscription_service] = lambda: push_svc

    response = client.patch("/api/push/topics", json={"auth": "", "topics": ["presence"]})

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# /notification-create — POST form handler (notification_ui)
# ---------------------------------------------------------------------------


def test_post_notification_create_redirects_to_preview(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})
    svc = _mock_notification_svc()
    svc.add.return_value = "nid-test-123"
    test_app.dependency_overrides[get_notification_service] = lambda: svc
    csrf_token = client.cookies.get("csrftoken")
    assert csrf_token is not None

    response = client.post(
        "/notification-create",
        data={"message": "Hello Welt", "x-csrf-token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "nid-test-123" in response.headers["location"]
    svc.add.assert_called_once()


def test_post_notification_create_empty_message_redirects_back(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})
    svc = _mock_notification_svc()
    test_app.dependency_overrides[get_notification_service] = lambda: svc
    csrf_token = client.cookies.get("csrftoken")
    assert csrf_token is not None

    response = client.post(
        "/notification-create",
        data={"message": "   ", "x-csrf-token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/notification-create")
    svc.add.assert_not_called()


def test_post_notification_create_invalid_date_redirects_back(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})
    svc = _mock_notification_svc()
    test_app.dependency_overrides[get_notification_service] = lambda: svc
    csrf_token = client.cookies.get("csrftoken")
    assert csrf_token is not None

    response = client.post(
        "/notification-create",
        data={"message": "Test", "valid_from": "not-a-date", "x-csrf-token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/notification-create")
    svc.add.assert_not_called()


def test_post_notification_create_redirects_to_auth_when_unauthenticated(
    client: TestClient,
    test_app: FastAPI,
) -> None:
    svc = _mock_notification_svc()
    test_app.dependency_overrides[get_notification_service] = lambda: svc

    response = client.post("/notification-create", data={"message": "Hello"}, follow_redirects=False)

    assert response.status_code in (302, 303)
    assert "/auth" in response.headers["location"]


# ---------------------------------------------------------------------------
# /preview/notifications — GET preview page (notification_ui)
# ---------------------------------------------------------------------------


def test_get_notification_preview_renders_page(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})
    svc = _mock_notification_svc()
    notification = MagicMock()
    notification.id = "nid-test-abc"
    notification.is_outdated.return_value = False
    notification.enabled = False
    svc.get.return_value = [notification]
    test_app.dependency_overrides[get_notification_service] = lambda: svc

    response = client.get("/preview/notifications?n_ids=nid-test-abc")

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# /preview/notifications/{id}/enable — POST (notification_ui)
# ---------------------------------------------------------------------------


def test_enable_notification_redirects_to_preview(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})
    svc = _mock_notification_svc()
    svc.update.return_value = True
    test_app.dependency_overrides[get_notification_service] = lambda: svc
    csrf_token = client.cookies.get("csrftoken")
    assert csrf_token is not None

    response = client.post(
        "/preview/notifications/nid-test/enable",
        data={"x-csrf-token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "nid-test" in response.headers["location"]
    svc.update.assert_called_once_with("nid-test", enabled=True)


def test_enable_notification_returns_404_when_not_found(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})
    svc = _mock_notification_svc()
    svc.update.return_value = False
    test_app.dependency_overrides[get_notification_service] = lambda: svc
    csrf_token = client.cookies.get("csrftoken")
    assert csrf_token is not None

    response = client.post(
        "/preview/notifications/nid-unknown/enable",
        data={"x-csrf-token": csrf_token},
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# /preview/notifications/{id}/disable — POST (notification_ui)
# ---------------------------------------------------------------------------


def test_disable_notification_redirects_to_preview(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})
    svc = _mock_notification_svc()
    svc.update.return_value = True
    test_app.dependency_overrides[get_notification_service] = lambda: svc
    csrf_token = client.cookies.get("csrftoken")
    assert csrf_token is not None

    response = client.post(
        "/preview/notifications/nid-test/disable",
        data={"x-csrf-token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "nid-test" in response.headers["location"]
    svc.update.assert_called_once_with("nid-test", enabled=False)


def test_disable_notification_returns_404_when_not_found(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})
    svc = _mock_notification_svc()
    svc.update.return_value = False
    test_app.dependency_overrides[get_notification_service] = lambda: svc
    csrf_token = client.cookies.get("csrftoken")
    assert csrf_token is not None

    response = client.post(
        "/preview/notifications/nid-unknown/disable",
        data={"x-csrf-token": csrf_token},
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# /preview/notifications/{id}/delete — POST (notification_ui)
# ---------------------------------------------------------------------------


def test_delete_notification_action_redirects_to_preview(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})
    svc = _mock_notification_svc()
    svc.delete.return_value = True
    test_app.dependency_overrides[get_notification_service] = lambda: svc
    csrf_token = client.cookies.get("csrftoken")
    assert csrf_token is not None

    response = client.post(
        "/preview/notifications/nid-test/delete",
        data={"x-csrf-token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "preview/notifications" in response.headers["location"]
    svc.delete.assert_called_once_with("nid-test")


def test_delete_notification_action_returns_404_when_not_found(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})
    svc = _mock_notification_svc()
    svc.delete.return_value = False
    test_app.dependency_overrides[get_notification_service] = lambda: svc
    csrf_token = client.cookies.get("csrftoken")
    assert csrf_token is not None

    response = client.post(
        "/preview/notifications/nid-unknown/delete",
        data={"x-csrf-token": csrf_token},
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# /preview/notifications/content — GET HTML fragment (notification_ui)
# ---------------------------------------------------------------------------


def test_get_notification_preview_content_returns_html(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})
    svc = _mock_notification_svc()
    n1 = MagicMock()
    n1.id = "nid-1"
    n1.message = "Hello **World**"
    n2 = MagicMock()
    n2.id = "nid-2"
    n2.message = "Test"
    svc.get.return_value = [n1, n2]
    test_app.dependency_overrides[get_notification_service] = lambda: svc

    response = client.get("/preview/notifications/content?n_ids=nid-1&n_ids=nid-2")

    assert response.status_code == 200
    assert "Hello" in response.text


def test_get_notification_preview_content_returns_empty_when_no_notifications(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})
    svc = _mock_notification_svc()
    svc.get.return_value = []
    test_app.dependency_overrides[get_notification_service] = lambda: svc

    response = client.get("/preview/notifications/content?n_ids=nid-none")

    assert response.status_code == 200
    assert response.text == ""
