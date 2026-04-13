"""Tests for app.env load() / validate()."""

from pathlib import Path

import pytest

from app import env


@pytest.fixture
def env_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Set LOCAL_DATA_PATH and API_KEYS_PATH to real temp-dir paths."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    keys_file = tmp_path / "keys.json"
    monkeypatch.setenv("LOCAL_DATA_PATH", str(data_dir))
    monkeypatch.setenv("API_KEYS_PATH", str(keys_file))
    return data_dir, keys_file


def test_validate_raises_when_required_vars_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SESSION_SECRET_KEY", raising=False)
    monkeypatch.delenv("LOCAL_DATA_PATH", raising=False)
    monkeypatch.delenv("API_KEYS_PATH", raising=False)

    with pytest.raises(RuntimeError, match="SESSION_SECRET_KEY"):
        env.validate()


def test_validate_passes_when_all_required_vars_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SESSION_SECRET_KEY", "a" * env.MIN_TOKEN_LENGTH)
    monkeypatch.setenv("APP_URL", "https://status.example.com")

    env.validate()  # should not raise


def test_load_refreshes_module_globals(monkeypatch: pytest.MonkeyPatch, env_paths: tuple[Path, Path]) -> None:
    data_dir, keys_file = env_paths
    monkeypatch.setenv("SESSION_SECRET_KEY", "refreshed-secret")

    env.load()

    assert env.SESSION_SECRET_KEY == "refreshed-secret"  # noqa: S105
    assert str(data_dir) == env.LOCAL_DATA_PATH
    assert str(keys_file) == env.API_KEYS_PATH


def test_load_optional_int_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PRESENCE_POLLING_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("INTERNAL_POLLING_INTERVAL_SECONDS", raising=False)

    env.load()

    assert env.PRESENCE_POLLING_INTERVAL_SECONDS == 60
    assert env.INTERNAL_POLLING_INTERVAL_SECONDS == 60


def test_load_optional_int_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRESENCE_POLLING_INTERVAL_SECONDS", "120")

    env.load()

    assert env.PRESENCE_POLLING_INTERVAL_SECONDS == 120


def test_load_https_only_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTPS_ONLY", "true")
    env.load()
    assert env.HTTPS_ONLY is True


def test_load_https_only_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTPS_ONLY", "false")
    env.load()
    assert env.HTTPS_ONLY is False


def test_load_router_creds_empty_string_becomes_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROUTER_IP", "")
    monkeypatch.setenv("ROUTER_USERNAME", "")
    env.load()
    assert env.ROUTER_IP is None
    assert env.ROUTER_USERNAME is None


def test_load_vapid_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "private")
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "public")
    monkeypatch.setenv("VAPID_CLAIM_SUBJECT", "https://example.com")

    env.load()

    assert env.VAPID_PRIVATE_KEY == "private"
    assert env.VAPID_PUBLIC_KEY == "public"
    assert env.VAPID_CLAIM_SUBJECT == "https://example.com"


def test_load_show_auth_button_default_is_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHOW_AUTH_BUTTON", raising=False)
    env.load()
    assert env.SHOW_AUTH_BUTTON is False


def test_load_show_auth_button_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHOW_AUTH_BUTTON", "true")
    env.load()
    assert env.SHOW_AUTH_BUTTON is True


def test_load_admin_token_default_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    env.load()
    assert env.ADMIN_TOKEN is None


def test_load_admin_token_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_TOKEN", "some-token-value")
    env.load()
    assert env.ADMIN_TOKEN == "some-token-value"  # noqa: S105


def test_validate_raises_when_admin_token_too_short(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SESSION_SECRET_KEY", "a" * env.MIN_TOKEN_LENGTH)
    monkeypatch.setenv("ADMIN_TOKEN", "short")
    with pytest.raises(RuntimeError, match="ADMIN_TOKEN"):
        env.validate()


def test_validate_passes_when_admin_token_meets_minimum_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SESSION_SECRET_KEY", "a" * env.MIN_TOKEN_LENGTH)
    monkeypatch.setenv("ADMIN_TOKEN", "a" * env.MIN_TOKEN_LENGTH)
    env.validate()  # should not raise


def test_validate_raises_when_session_secret_key_too_short(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SESSION_SECRET_KEY", "short")
    with pytest.raises(RuntimeError, match="SESSION_SECRET_KEY"):
        env.validate()


def test_feature_presence_true_when_all_router_creds_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROUTER_IP", "192.168.1.1")
    monkeypatch.setenv("ROUTER_USERNAME", "admin")
    monkeypatch.setenv("ROUTER_PASSWORD", "secret")
    env.load()
    assert env.is_presence_enabled() is True


def test_feature_presence_false_when_any_router_cred_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROUTER_IP", "192.168.1.1")
    monkeypatch.delenv("ROUTER_USERNAME", raising=False)
    monkeypatch.delenv("ROUTER_PASSWORD", raising=False)
    env.load()
    assert env.is_presence_enabled() is False


def test_feature_push_true_when_all_vapid_vars_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "private")
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "public")
    monkeypatch.setenv("VAPID_CLAIM_SUBJECT", "https://example.com")
    env.load()
    assert env.is_push_enabled() is True


def test_feature_push_false_when_any_vapid_var_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "private")
    monkeypatch.delenv("VAPID_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("VAPID_CLAIM_SUBJECT", raising=False)
    env.load()
    assert env.is_push_enabled() is False


def test_feature_weather_true_when_all_owm_vars_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENWEATHERMAP_API_KEY", "apikey")
    monkeypatch.setenv("WEATHER_LAT", "48.3")
    monkeypatch.setenv("WEATHER_LON", "10.9")
    env.load()
    assert env.is_weather_enabled() is True


def test_feature_weather_false_when_any_owm_var_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENWEATHERMAP_API_KEY", "apikey")
    monkeypatch.delenv("WEATHER_LAT", raising=False)
    monkeypatch.delenv("WEATHER_LON", raising=False)
    env.load()
    assert env.is_weather_enabled() is False


def test_feature_legal_page_true_when_both_operator_vars_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPERATOR_NAME", "Max Mustermann")
    monkeypatch.setenv("OPERATOR_EMAIL", "max@example.com")
    env.load()
    assert env.is_legal_page_enabled() is True


def test_feature_legal_page_false_when_any_operator_var_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPERATOR_NAME", "Max Mustermann")
    monkeypatch.delenv("OPERATOR_EMAIL", raising=False)
    env.load()
    assert env.is_legal_page_enabled() is False


def test_feature_login_button_true_when_show_auth_button_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHOW_AUTH_BUTTON", "true")
    env.load()
    assert env.is_login_button_enabled() is True


def test_feature_login_button_false_when_show_auth_button_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHOW_AUTH_BUTTON", raising=False)
    env.load()
    assert env.is_login_button_enabled() is False
