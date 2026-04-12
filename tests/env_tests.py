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


def test_load_show_admin_auth_default_is_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHOW_ADMIN_AUTH", raising=False)
    env.load()
    assert env.SHOW_ADMIN_AUTH is False


def test_load_show_admin_auth_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHOW_ADMIN_AUTH", "true")
    env.load()
    assert env.SHOW_ADMIN_AUTH is True


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
