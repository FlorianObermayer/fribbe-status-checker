import os
import tempfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import ValidationError
import pytest

from app.api.EphemeralAPIKeyStore import EphemeralAPIKeyStore
from app.api.Responses import ApiKey


@pytest.fixture(scope="session", autouse=True)
def set_env():
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["API_KEYS_PATH"] = os.path.join(tmpdir, "apikeys.test.json")


def test_is_key_valid():
    now = datetime.now(tz=ZoneInfo("Europe/Berlin"))
    valid_key = ApiKey(
        key="02552721-61c1-4535-979e-fb57c8f3c3f0-valid",
        comment="",
        valid_until=(now + timedelta(days=1)).replace(microsecond=0),
    )
    expired_key = ApiKey(
        key="02552721-61c1-4535-979e-fb57c8f3c3f0-outdated",
        comment="",
        valid_until=(now - timedelta(days=1)).replace(microsecond=0),
    )
    EphemeralAPIKeyStore.save(
        [
            valid_key,
            expired_key,
        ]
    )
    assert EphemeralAPIKeyStore.is_key_valid("02552721-61c1-4535-979e-fb57c8f3c3f0-valid") is True
    assert EphemeralAPIKeyStore.is_key_valid("02552721-61c1-4535-979e-fb57c8f3c3f0-outdated") is False 
    assert EphemeralAPIKeyStore.is_key_valid("02552721-61c1-4535-979e-fb57c8f3c3f0-notfound") is False
    assert EphemeralAPIKeyStore.is_key_valid("notfound") is False


def test_key_too_short():
    with pytest.raises(ValidationError):
        ApiKey(
            key="too_short",
            comment="",
            valid_until=datetime.now(tz=ZoneInfo("Europe/Berlin")),
        )
