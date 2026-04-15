from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app import env
from app.api.access_role import AccessRole
from app.api.ephemeral_api_key_store import EphemeralAPIKeyStore, RemoveResult
from app.api.responses import ApiKey


def test_is_key_valid() -> None:
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
        ],
    )
    assert EphemeralAPIKeyStore.is_key_valid("4w69446-02552721-61c1-4535-979e-fb57c8f3c3f0-valid") is True
    assert EphemeralAPIKeyStore.is_key_valid("4w69446-02552721-61c1-4535-979e-fb57c8f3c3f0-outdated") is False
    assert EphemeralAPIKeyStore.is_key_valid("4w69446-02552721-61c1-4535-979e-fb57c8f3c3f0-notfound") is False
    assert EphemeralAPIKeyStore.is_key_valid("notfound") is False


def test_is_key_valid_naive_datetime() -> None:
    now_naive = datetime.now()  # no tzinfo
    valid_key = ApiKey(
        key="4w69446-02552721-61c1-4535-979e-fb57c8f3c3f0-naive-valid",
        comment="",
        valid_until=(now_naive + timedelta(days=1)).replace(microsecond=0),
    )
    expired_key = ApiKey(
        key="4w69446-02552721-61c1-4535-979e-fb57c8f3c3f0-naive-expired",
        comment="",
        valid_until=(now_naive - timedelta(days=1)).replace(microsecond=0),
    )
    EphemeralAPIKeyStore.save([valid_key, expired_key])
    assert EphemeralAPIKeyStore.is_key_valid("4w69446-02552721-61c1-4535-979e-fb57c8f3c3f0-naive-valid") is True
    assert EphemeralAPIKeyStore.is_key_valid("4w69446-02552721-61c1-4535-979e-fb57c8f3c3f0-naive-expired") is False


def test_get_valid_key_role_naive_datetime() -> None:
    now_naive = datetime.now()  # no tzinfo
    valid_key = ApiKey(
        key="4w69446-02552721-61c1-4535-979e-fb57c8f3c3f0-role-naive-valid",
        comment="",
        valid_until=(now_naive + timedelta(days=1)).replace(microsecond=0),
    )
    expired_key = ApiKey(
        key="4w69446-02552721-61c1-4535-979e-fb57c8f3c3f0-role-naive-expired",
        comment="",
        valid_until=(now_naive - timedelta(days=1)).replace(microsecond=0),
    )
    EphemeralAPIKeyStore.save([valid_key, expired_key])
    assert (
        EphemeralAPIKeyStore.get_valid_key_role("4w69446-02552721-61c1-4535-979e-fb57c8f3c3f0-role-naive-valid")
        is not None
    )
    assert (
        EphemeralAPIKeyStore.get_valid_key_role("4w69446-02552721-61c1-4535-979e-fb57c8f3c3f0-role-naive-expired")
        is None
    )


def test_key_too_short() -> None:
    with pytest.raises(ValidationError):
        ApiKey(
            key="too_short",
            comment="",
            valid_until=datetime.now(tz=ZoneInfo("Europe/Berlin")),
        )


def test_generate_new_returns_valid_api_key() -> None:

    valid_until = datetime.now(tz=ZoneInfo("Europe/Berlin")) + timedelta(days=30)
    api_key = ApiKey.generate_new(comment="test", valid_until=valid_until)

    assert len(api_key.key) >= env.MIN_TOKEN_LENGTH
    assert api_key.comment == "test"
    assert api_key.valid_until == valid_until


def test_generate_new_keys_are_unique() -> None:
    valid_until = datetime.now(tz=ZoneInfo("Europe/Berlin")) + timedelta(days=30)
    key_a = ApiKey.generate_new(comment="", valid_until=valid_until)
    key_b = ApiKey.generate_new(comment="", valid_until=valid_until)

    assert key_a.key != key_b.key


def test_append_adds_key_to_store() -> None:
    EphemeralAPIKeyStore.save([])
    key = ApiKey.generate_new(comment="", valid_until=datetime.now(tz=ZoneInfo("Europe/Berlin")) + timedelta(days=1))

    result = EphemeralAPIKeyStore.append(key)

    assert result is True
    assert EphemeralAPIKeyStore.is_key_valid(key.key) is True


def test_append_returns_false_when_save_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    EphemeralAPIKeyStore.save([])
    key = ApiKey.generate_new(comment="", valid_until=datetime.now(tz=ZoneInfo("Europe/Berlin")) + timedelta(days=1))

    def _raise(_: list[ApiKey]) -> None:
        msg = "disk full"
        raise OSError(msg)

    monkeypatch.setattr(EphemeralAPIKeyStore, "save", staticmethod(_raise))

    result = EphemeralAPIKeyStore.append(key)

    assert result is False


def _make_key(comment: str = "") -> ApiKey:
    return ApiKey.generate_new(
        comment=comment,
        valid_until=datetime.now(tz=ZoneInfo("Europe/Berlin")) + timedelta(days=1),
    )


def test_remove_returns_not_found_when_no_match() -> None:
    EphemeralAPIKeyStore.save([])
    assert EphemeralAPIKeyStore.remove("nonexistent-prefix") == RemoveResult.NOT_FOUND


def test_remove_deletes_unique_match() -> None:
    key = _make_key()
    EphemeralAPIKeyStore.save([key])

    assert EphemeralAPIKeyStore.remove(key.key[:10]) == RemoveResult.DELETED
    assert EphemeralAPIKeyStore.is_empty()


def test_remove_returns_ambiguous_when_multiple_matches() -> None:
    key_a = _make_key("a")
    key_b = _make_key("b")
    # Ensure both share a common prefix by constructing keys manually

    shared_prefix = "sharedprefix-"
    suffix_a = "a" * (env.MIN_TOKEN_LENGTH - len(shared_prefix))
    suffix_b = "b" * (env.MIN_TOKEN_LENGTH - len(shared_prefix))
    key_a = ApiKey(key=shared_prefix + suffix_a, comment="a", valid_until=key_a.valid_until)
    key_b = ApiKey(key=shared_prefix + suffix_b, comment="b", valid_until=key_b.valid_until)
    EphemeralAPIKeyStore.save([key_a, key_b])

    assert EphemeralAPIKeyStore.remove(shared_prefix) == RemoveResult.AMBIGUOUS
    assert len(EphemeralAPIKeyStore.load()) == 2


# ---------------------------------------------------------------------------
# has_valid_admin_key
# ---------------------------------------------------------------------------


def test_has_valid_admin_key_empty_store() -> None:
    EphemeralAPIKeyStore.save([])
    assert EphemeralAPIKeyStore.has_valid_admin_key() is False


def test_has_valid_admin_key_non_admin_role() -> None:
    key = ApiKey.generate_new(
        comment="reader",
        valid_until=datetime.now(tz=ZoneInfo("Europe/Berlin")) + timedelta(days=1),
        role=AccessRole.READER,
    )
    EphemeralAPIKeyStore.save([key])
    assert EphemeralAPIKeyStore.has_valid_admin_key() is False


def test_has_valid_admin_key_expired_admin() -> None:
    key = ApiKey.generate_new(
        comment="expired admin",
        valid_until=datetime.now(tz=ZoneInfo("Europe/Berlin")) - timedelta(days=1),
        role=AccessRole.ADMIN,
    )
    EphemeralAPIKeyStore.save([key])
    assert EphemeralAPIKeyStore.has_valid_admin_key() is False


def test_has_valid_admin_key_valid_admin() -> None:
    key = ApiKey.generate_new(
        comment="valid admin",
        valid_until=datetime.now(tz=ZoneInfo("Europe/Berlin")) + timedelta(days=1),
        role=AccessRole.ADMIN,
    )
    EphemeralAPIKeyStore.save([key])
    assert EphemeralAPIKeyStore.has_valid_admin_key() is True
