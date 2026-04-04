from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.api.EphemeralAPIKeyStore import EphemeralAPIKeyStore
from app.api.Responses import ApiKey


def test_is_key_valid():
    now = datetime.now(tz=ZoneInfo("Europe/Berlin"))
    valid_key = ApiKey(
        key="4w69446-02552721-61c1-4535-979e-fb57c8f3c3f0-valid",
        comment="",
        valid_until=(now + timedelta(days=1)).replace(microsecond=0),
    )
    expired_key = ApiKey(
        key="4w69446-02552721-61c1-4535-979e-fb57c8f3c3f0-outdated",
        comment="",
        valid_until=(now - timedelta(days=1)).replace(microsecond=0),
    )
    EphemeralAPIKeyStore.save(
        [
            valid_key,
            expired_key,
        ]
    )
    assert EphemeralAPIKeyStore.is_key_valid("4w69446-02552721-61c1-4535-979e-fb57c8f3c3f0-valid") is True
    assert EphemeralAPIKeyStore.is_key_valid("4w69446-02552721-61c1-4535-979e-fb57c8f3c3f0-outdated") is False
    assert EphemeralAPIKeyStore.is_key_valid("4w69446-02552721-61c1-4535-979e-fb57c8f3c3f0-notfound") is False
    assert EphemeralAPIKeyStore.is_key_valid("notfound") is False


def test_key_too_short():
    with pytest.raises(ValidationError):
        ApiKey(
            key="too_short",
            comment="",
            valid_until=datetime.now(tz=ZoneInfo("Europe/Berlin")),
        )


def test_generate_new_returns_valid_api_key():
    from app import env

    valid_until = datetime.now(tz=ZoneInfo("Europe/Berlin")) + timedelta(days=30)
    api_key = ApiKey.generate_new(comment="test", valid_until=valid_until)

    assert len(api_key.key) >= env.MIN_TOKEN_LENGTH
    assert api_key.comment == "test"
    assert api_key.valid_until == valid_until


def test_generate_new_keys_are_unique():
    valid_until = datetime.now(tz=ZoneInfo("Europe/Berlin")) + timedelta(days=30)
    key_a = ApiKey.generate_new(comment="", valid_until=valid_until)
    key_b = ApiKey.generate_new(comment="", valid_until=valid_until)

    assert key_a.key != key_b.key


def test_append_adds_key_to_store():
    EphemeralAPIKeyStore.save([])
    key = ApiKey.generate_new(comment="", valid_until=datetime.now(tz=ZoneInfo("Europe/Berlin")) + timedelta(days=1))

    result = EphemeralAPIKeyStore.append(key)

    assert result is True
    assert EphemeralAPIKeyStore.is_key_valid(key.key) is True


def test_append_require_empty_succeeds_when_store_is_empty():
    EphemeralAPIKeyStore.save([])
    key = ApiKey.generate_new(comment="", valid_until=datetime.now(tz=ZoneInfo("Europe/Berlin")) + timedelta(days=1))

    result = EphemeralAPIKeyStore.append(key, require_empty=True)

    assert result is True
    assert EphemeralAPIKeyStore.is_key_valid(key.key) is True


def test_append_require_empty_fails_when_store_is_not_empty():
    existing = ApiKey.generate_new(
        comment="existing", valid_until=datetime.now(tz=ZoneInfo("Europe/Berlin")) + timedelta(days=1)
    )
    EphemeralAPIKeyStore.save([existing])
    new_key = ApiKey.generate_new(
        comment="new", valid_until=datetime.now(tz=ZoneInfo("Europe/Berlin")) + timedelta(days=1)
    )

    result = EphemeralAPIKeyStore.append(new_key, require_empty=True)

    assert result is False
    assert EphemeralAPIKeyStore.is_key_valid(new_key.key) is False


def test_append_returns_false_when_save_raises(monkeypatch: pytest.MonkeyPatch):
    EphemeralAPIKeyStore.save([])
    key = ApiKey.generate_new(comment="", valid_until=datetime.now(tz=ZoneInfo("Europe/Berlin")) + timedelta(days=1))

    def _raise(_: list[ApiKey]) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(EphemeralAPIKeyStore, "save", staticmethod(_raise))

    result = EphemeralAPIKeyStore.append(key)

    assert result is False
