"""Tests for app.api.redact — token redaction helper."""

import pytest

from app.api.redact import redact_key


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        (None, "<none>"),
        ("", "<empty>"),
        ("abcdefghijklmnopqrstuvwxyz0123456789abcdefghijklmnop", "abcdefgh…"),
    ],
)
def test_redact_key(key: str | None, expected: str) -> None:
    assert redact_key(key) == expected
