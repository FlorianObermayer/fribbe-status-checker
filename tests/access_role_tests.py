"""Tests for role-based access control (AccessRole enum + HybridAuth min_role).

Each test creates an API key with a specific role, authenticates with it,
and verifies that access is granted or denied based on the endpoint's
required minimum role.
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import env
from app.api.access_role import AccessRole
from app.api.ephemeral_api_key_store import EphemeralAPIKeyStore
from app.api.responses import ApiKey, MaskedApiKey
from app.dependencies import get_internal_service, get_notification_service
from tests.conftest import TEST_ADMIN_TOKEN

_UTC = ZoneInfo("UTC")
_NOW = datetime(2026, 4, 13, 12, 0, 0, tzinfo=_UTC)


def _make_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role: AccessRole) -> ApiKey:
    """Create and persist an API key with the given role."""
    keys_path = tmp_path / "api_keys.json"
    monkeypatch.setattr(env, "API_KEYS_PATH", str(keys_path))
    api_key = ApiKey.generate_new(
        comment=f"test-{role.name}",
        valid_until=datetime(2030, 12, 31, tzinfo=_UTC),
        role=role,
    )
    EphemeralAPIKeyStore.save([api_key])
    return api_key


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
    svc = MagicMock()
    svc.list_all.return_value = []
    svc.add.return_value = "nid-test"
    return svc


# ---------------------------------------------------------------------------
# AccessRole enum ordering
# ---------------------------------------------------------------------------


def test_access_role_ordering() -> None:
    assert AccessRole.READER < AccessRole.NOTIFICATION_OPERATOR < AccessRole.ADMIN


# ---------------------------------------------------------------------------
# ApiKey role field — serialisation round-trip
# ---------------------------------------------------------------------------


def test_api_key_role_defaults_to_admin() -> None:
    key = ApiKey(
        key="A" * env.MIN_TOKEN_LENGTH,
        comment="test",
        valid_until=datetime(2030, 1, 1, tzinfo=_UTC),
    )
    assert key.role == AccessRole.ADMIN


def test_api_key_to_dict_includes_role() -> None:
    key = ApiKey(
        key="A" * env.MIN_TOKEN_LENGTH,
        comment="t",
        valid_until=datetime(2030, 1, 1, tzinfo=_UTC),
        role=AccessRole.NOTIFICATION_OPERATOR,
    )
    d = key.to_dict()
    assert d["role"] == "notification_operator"


def test_api_key_from_dict_parses_role() -> None:
    d = {
        "key": "A" * env.MIN_TOKEN_LENGTH,
        "comment": "",
        "valid_until": "2030-01-01T00:00:00+00:00",
        "role": "reader",
    }
    key = ApiKey.from_dict(d)
    assert key.role == AccessRole.READER


def test_api_key_from_dict_missing_role_defaults_to_admin() -> None:
    d = {
        "key": "A" * env.MIN_TOKEN_LENGTH,
        "comment": "",
        "valid_until": "2030-01-01T00:00:00+00:00",
    }
    key = ApiKey.from_dict(d)
    assert key.role == AccessRole.ADMIN


def test_api_key_generate_new_default_role_is_reader() -> None:
    key = ApiKey.generate_new(
        comment="test",
        valid_until=datetime(2030, 1, 1, tzinfo=_UTC),
    )
    assert key.role == AccessRole.READER


def test_api_key_generate_new_explicit_role() -> None:
    key = ApiKey.generate_new(
        comment="test",
        valid_until=datetime(2030, 1, 1, tzinfo=_UTC),
        role=AccessRole.NOTIFICATION_OPERATOR,
    )
    assert key.role == AccessRole.NOTIFICATION_OPERATOR


# ---------------------------------------------------------------------------
# get_valid_key_role
# ---------------------------------------------------------------------------


def test_get_valid_key_role_returns_role_for_valid_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api_key = _make_key(tmp_path, monkeypatch, AccessRole.NOTIFICATION_OPERATOR)
    assert EphemeralAPIKeyStore.get_valid_key_role(api_key.key) == AccessRole.NOTIFICATION_OPERATOR


def test_get_valid_key_role_returns_none_for_expired_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys_path = tmp_path / "api_keys.json"
    monkeypatch.setattr(env, "API_KEYS_PATH", str(keys_path))
    api_key = ApiKey.generate_new(
        comment="expired",
        valid_until=datetime(2020, 1, 1, tzinfo=_UTC),
        role=AccessRole.ADMIN,
    )
    EphemeralAPIKeyStore.save([api_key])
    assert EphemeralAPIKeyStore.get_valid_key_role(api_key.key) is None


def test_get_valid_key_role_returns_none_for_unknown_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys_path = tmp_path / "api_keys.json"
    monkeypatch.setattr(env, "API_KEYS_PATH", str(keys_path))
    EphemeralAPIKeyStore.save([])
    assert EphemeralAPIKeyStore.get_valid_key_role("nonexistent") is None


def test_get_valid_key_role_returns_none_for_none() -> None:
    assert EphemeralAPIKeyStore.get_valid_key_role(None) is None


# ---------------------------------------------------------------------------
# READER role — read-only access
# ---------------------------------------------------------------------------


def test_reader_can_access_internal_details(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    api_key = _make_key(tmp_path, monkeypatch, AccessRole.READER)
    test_app.dependency_overrides[get_internal_service] = _mock_internal_svc

    response = client.get("/api/internal/details", headers={"api_key": api_key.key})

    assert response.status_code == 200


def test_reader_can_list_notifications(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    api_key = _make_key(tmp_path, monkeypatch, AccessRole.READER)
    test_app.dependency_overrides[get_notification_service] = _mock_notification_svc

    response = client.get("/api/notifications/list", headers={"api_key": api_key.key})

    assert response.status_code == 200


def test_reader_cannot_create_notification(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    api_key = _make_key(tmp_path, monkeypatch, AccessRole.READER)
    test_app.dependency_overrides[get_notification_service] = _mock_notification_svc

    response = client.post(
        "/api/notifications",
        json={"message": "test"},
        headers={"api_key": api_key.key},
    )

    assert response.status_code == 403


def test_reader_cannot_delete_notification(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    api_key = _make_key(tmp_path, monkeypatch, AccessRole.READER)
    test_app.dependency_overrides[get_notification_service] = _mock_notification_svc

    response = client.request(
        "DELETE",
        "/api/notifications/nid-test",
        headers={"api_key": api_key.key},
    )

    assert response.status_code == 403


def test_reader_cannot_update_config(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    api_key = _make_key(tmp_path, monkeypatch, AccessRole.READER)

    response = client.patch(
        "/internal/config",
        json={"threshold_min_non_empty_ct": 5},
        headers={"api_key": api_key.key},
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# NOTIFICATION_OPERATOR role
# ---------------------------------------------------------------------------


def test_notification_operator_can_read_details(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    api_key = _make_key(tmp_path, monkeypatch, AccessRole.NOTIFICATION_OPERATOR)
    test_app.dependency_overrides[get_internal_service] = _mock_internal_svc

    response = client.get("/api/internal/details", headers={"api_key": api_key.key})

    assert response.status_code == 200


def test_notification_operator_can_create_notification(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    api_key = _make_key(tmp_path, monkeypatch, AccessRole.NOTIFICATION_OPERATOR)
    test_app.dependency_overrides[get_notification_service] = _mock_notification_svc

    response = client.post(
        "/api/notifications",
        json={"message": "test"},
        headers={"api_key": api_key.key},
    )

    assert response.status_code == 200


def test_notification_operator_can_delete_notification(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    api_key = _make_key(tmp_path, monkeypatch, AccessRole.NOTIFICATION_OPERATOR)
    svc = _mock_notification_svc()
    svc.delete.return_value = True
    test_app.dependency_overrides[get_notification_service] = lambda: svc

    response = client.request(
        "DELETE",
        "/api/notifications/nid-test",
        headers={"api_key": api_key.key},
    )

    assert response.status_code == 200


def test_notification_operator_cannot_update_config(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    api_key = _make_key(tmp_path, monkeypatch, AccessRole.NOTIFICATION_OPERATOR)

    response = client.patch(
        "/internal/config",
        json={"threshold_min_non_empty_ct": 5},
        headers={"api_key": api_key.key},
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# ADMIN role — full access
# ---------------------------------------------------------------------------


def test_admin_token_accesses_reader_endpoint(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(env, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    test_app.dependency_overrides[get_internal_service] = _mock_internal_svc

    response = client.get("/api/internal/details", headers={"api_key": TEST_ADMIN_TOKEN})
    assert response.status_code == 200


def test_admin_token_accesses_notification_operator_endpoint(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(env, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    test_app.dependency_overrides[get_notification_service] = _mock_notification_svc

    response = client.post(
        "/api/notifications",
        json={"message": "test"},
        headers={"api_key": TEST_ADMIN_TOKEN},
    )
    assert response.status_code == 200


def test_admin_token_accesses_admin_endpoint(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(env, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)

    response = client.patch(
        "/internal/config",
        json={},
        headers={"api_key": TEST_ADMIN_TOKEN},
    )
    assert response.status_code == 304  # not modified (no thresholds set), but not 403


def test_admin_api_key_can_access_admin_endpoints(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    api_key = _make_key(tmp_path, monkeypatch, AccessRole.ADMIN)
    test_app.dependency_overrides[get_internal_service] = _mock_internal_svc

    response = client.get("/api/internal/details", headers={"api_key": api_key.key})

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Session-based role checks
# ---------------------------------------------------------------------------


def test_session_preserves_role_for_api_key(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """After header-based auth creates a session, session-only requests must honour the role."""
    api_key = _make_key(tmp_path, monkeypatch, AccessRole.READER)
    test_app.dependency_overrides[get_internal_service] = _mock_internal_svc
    test_app.dependency_overrides[get_notification_service] = _mock_notification_svc

    # Authenticate via header — creates a session
    assert client.get("/api/internal/details", headers={"api_key": api_key.key}).status_code == 200

    # Session-only request (no api_key header) — should inherit READER role
    assert client.get("/api/internal/details").status_code == 200  # READER can read
    assert client.post("/api/notifications", json={"message": "x"}).status_code == 403  # but can't create


def test_admin_session_via_form_login(
    client: TestClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Logging in with ADMIN_TOKEN via /auth should grant full ADMIN role."""
    monkeypatch.setattr(env, "ADMIN_TOKEN", TEST_ADMIN_TOKEN)
    test_app.dependency_overrides[get_notification_service] = _mock_notification_svc

    client.post("/auth", json={"token": TEST_ADMIN_TOKEN, "next": "/"})
    csrf_token = client.cookies.get("csrftoken")
    assert csrf_token is not None
    csrf_headers = {"x-csrf-token": csrf_token}

    response = client.post(
        "/api/notifications",
        json={"message": "admin-created"},
        headers=csrf_headers,
    )

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# MaskedApiKey includes role
# ---------------------------------------------------------------------------


def test_masked_api_key_includes_role() -> None:
    key = ApiKey(
        key="A" * env.MIN_TOKEN_LENGTH,
        comment="test",
        valid_until=datetime(2030, 1, 1, tzinfo=_UTC),
        role=AccessRole.NOTIFICATION_OPERATOR,
    )
    masked = MaskedApiKey.from_api_key(key)
    assert masked.role == AccessRole.NOTIFICATION_OPERATOR


# ---------------------------------------------------------------------------
# Persist + reload role through store
# ---------------------------------------------------------------------------


def test_role_persists_through_store_save_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys_path = tmp_path / "api_keys.json"
    monkeypatch.setattr(env, "API_KEYS_PATH", str(keys_path))

    key = ApiKey.generate_new(
        comment="persist-test",
        valid_until=datetime(2030, 1, 1, tzinfo=_UTC),
        role=AccessRole.NOTIFICATION_OPERATOR,
    )
    EphemeralAPIKeyStore.save([key])

    loaded = EphemeralAPIKeyStore.load()
    assert len(loaded) == 1
    assert loaded[0].role == AccessRole.NOTIFICATION_OPERATOR
