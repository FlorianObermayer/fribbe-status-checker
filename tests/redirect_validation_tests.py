"""Regression tests for ``AuthRedirectQuery.sanitize_url`` and the /auth redirect handler.

Covers the browser-normalization bypasses reported by the security assessment:
backslashes, ASCII tab/newline characters, userinfo and protocol-relative forms.
"""

from urllib.parse import parse_qs, urljoin, urlsplit

from fastapi.testclient import TestClient

from app.api.requests import AuthRedirectQuery

_BASE = "https://status.example"


def _resolves_off_origin(value: str) -> bool:
    """Return True if *value* would navigate a browser away from the app origin."""
    base_scheme, base_netloc = urlsplit(_BASE).scheme, urlsplit(_BASE).netloc
    resolved = urlsplit(urljoin(_BASE, value))
    return (resolved.scheme, resolved.netloc) != (base_scheme, base_netloc)


# Payloads that previously passed the naive prefix check and resolved off-origin.
_OFF_ORIGIN_PAYLOADS = [
    "/\\evil.com",
    "/\t/evil.com",
    "/\n/evil.com",
    "/\r/evil.com",
    "/\\@evil.com",
    "/\\evil.com@good.example",
    "//evil.com",
    "///evil.com",
    "https://evil.com",
    "javascript:alert(1)",
    "data:text/html,x",
    "relative/path",
    "",
]

_SAFE_PAYLOADS = [
    "/",
    "/legit",
    "/notification-create?n_ids=nid-1",
    "/preview/notifications?n_ids=all_active&x=1",
]


def test_off_origin_payloads_are_replaced_with_root() -> None:
    for payload in _OFF_ORIGIN_PAYLOADS:
        assert AuthRedirectQuery.sanitize_url(payload) == "/", payload


def test_sanitized_values_never_resolve_off_origin() -> None:
    for payload in _OFF_ORIGIN_PAYLOADS:
        sanitized = AuthRedirectQuery.sanitize_url(payload)
        assert sanitized is not None
        assert not _resolves_off_origin(sanitized), payload


def test_safe_payloads_are_preserved() -> None:
    for payload in _SAFE_PAYLOADS:
        assert AuthRedirectQuery.sanitize_url(payload) == payload


def test_none_passes_through() -> None:
    assert AuthRedirectQuery.sanitize_url(None) is None


def test_backslash_is_treated_as_path_separator() -> None:
    assert AuthRedirectQuery.sanitize_url("/a\\b") == "/a/b"


def test_control_characters_are_stripped() -> None:
    assert AuthRedirectQuery.sanitize_url("/legit\t") == "/legit"


def test_field_validator_replaces_off_origin_with_root() -> None:
    for payload in _OFF_ORIGIN_PAYLOADS:
        assert AuthRedirectQuery(next=payload).next == "/", payload


def test_field_validator_preserves_safe_payload() -> None:
    assert AuthRedirectQuery(next="/notification-create").next == "/notification-create"


def test_redirect_handler_fully_encodes_next(client: TestClient) -> None:
    """An injected ``&next=`` in a protected URL must not create a second parameter."""
    response = client.get("/api-keys?x=1&next=//evil.com", follow_redirects=False)

    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("/auth?next=")

    query = parse_qs(urlsplit(location).query)
    assert query["next"] == ["/api-keys?x=1&next=//evil.com"]


def test_auth_page_preserves_legitimate_next(client: TestClient) -> None:
    response = client.get("/auth?next=/notification-create")

    assert response.status_code == 200
    assert 'data-next="/notification-create"' in response.text
