"""Tests for shared page utilities: show_toast and _read_toast_from_request."""

import json
from unittest.mock import MagicMock

from starlette.responses import Response

from app.routers._page_utils import _read_toast_from_request, show_toast

# ---------------------------------------------------------------------------
# show_toast()
# ---------------------------------------------------------------------------


def test_show_toast_sets_flash_cookie_with_default_success_type() -> None:
    response = Response()

    show_toast(response, "Vorschau erstellt")

    cookie_header = response.headers.get("set-cookie", "")
    assert "flash=" in cookie_header
    assert "max-age=" in cookie_header.lower()


def test_show_toast_sets_flash_cookie_with_error_type() -> None:
    response = Response()

    show_toast(response, "Pflichtfeld fehlt", "error")

    cookie_header = response.headers.get("set-cookie", "")
    assert "flash=" in cookie_header


# ---------------------------------------------------------------------------
# _read_toast_from_request()
# ---------------------------------------------------------------------------


def test_read_toast_returns_message_and_success_type() -> None:
    request = MagicMock()
    request.cookies = {"flash": json.dumps({"message": "Gespeichert", "type": "success"})}

    message, type_ = _read_toast_from_request(request)

    assert message == "Gespeichert"
    assert type_ == "success"


def test_read_toast_returns_message_and_error_type() -> None:
    request = MagicMock()
    request.cookies = {"flash": json.dumps({"message": "Fehler aufgetreten", "type": "error"})}

    message, type_ = _read_toast_from_request(request)

    assert message == "Fehler aufgetreten"
    assert type_ == "error"


def test_read_toast_returns_defaults_for_empty_cookie() -> None:
    request = MagicMock()
    request.cookies = {}

    message, type_ = _read_toast_from_request(request)

    assert message == ""
    assert type_ == "success"


def test_read_toast_returns_defaults_for_malformed_json() -> None:
    request = MagicMock()
    request.cookies = {"flash": "not-valid-json"}

    message, type_ = _read_toast_from_request(request)

    assert message == ""
    assert type_ == "success"
