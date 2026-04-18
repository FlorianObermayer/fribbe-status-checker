"""Tests for app.api.redact — sensitive data redaction helper."""

import hashlib
import hmac

import pytest

from app.api.redact import _SALT, redact


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "<none>"),
        ("", "<empty>"),
    ],
)
def test_redact_sentinels(value: str | None, expected: str) -> None:
    assert redact(value) == expected


def test_redact_format() -> None:
    result = redact("abc")
    assert result.startswith("[hash:")
    assert result.endswith("]")
    assert len(result) == len("[hash:]") + 8  # "[hash:" + 8 hex chars + "]"


def test_redact_same_value_consistent() -> None:
    """Same value hashes to same output within the same process."""
    assert redact("abc") == redact("abc")


def test_redact_different_values_differ() -> None:
    assert redact("abc") != redact("xyz")


def test_redact_uses_salt() -> None:
    """Output must match HMAC-SHA-256 of the value with the module salt."""
    value = "abc"
    expected_digest = hmac.new(_SALT, value.encode(), hashlib.sha256).hexdigest()[:8]
    assert redact(value) == f"[hash:{expected_digest}]"
