import os
import tempfile
from datetime import datetime, timedelta

from app.api.EphemeralAPIKeyStore import EphemeralAPIKeyStore
from app.api.EphemeralAPIKeyHeader import EphemeralAPIKeyHeader


def test_is_key_valid():
    with tempfile.NamedTemporaryFile() as tmp:
        os.environ["API_KEYS_PATH"] = tmp.name
        now = datetime.now()
        valid_key = {
            "key": "val123",
            "comment": "",
            "valid_until": (now + timedelta(days=1)).replace(microsecond=0).isoformat(),
        }
        expired_key = {
            "key": "exp123",
            "comment": "",
            "valid_until": (now - timedelta(days=1)).replace(microsecond=0).isoformat(),
        }
        illegal_format_no_valid_until = {
            "key": "illegal_format_no_valid_until",
            "comment": "",
        }
        illegal_format_no_valid_until_iso_format = {
            "key": "illegal_format_no_valid_until_iso_format",
            "comment": "",
            "valid_until": "tomorrow",
        }
        illegal_format_valid_until_is_none = {  # type: ignore
            "key": "illegal_format_valid_until_is_none",
            "comment": "",
            "valid_until": None,
        }
        EphemeralAPIKeyStore.save(
            [
                valid_key,
                expired_key,
                illegal_format_no_valid_until,
                illegal_format_no_valid_until_iso_format,
                illegal_format_valid_until_is_none,
            ]
        )
        EphemeralAPIKeyHeader.refresh_api_keys()
        header = EphemeralAPIKeyHeader()
        assert header._is_key_valid("val123") is True  # type: ignore
        assert header._is_key_valid("exp123") is False  # type: ignore
        assert header._is_key_valid("notfound") is False  # type: ignore
        assert header._is_key_valid("illegal_format_no_valid_until") is False  # type: ignore
        assert header._is_key_valid("illegal_format_no_valid_until_iso_format") is False  # type: ignore
        assert header._is_key_valid("illegal_format_valid_until_is_none") is False  # type: ignore
