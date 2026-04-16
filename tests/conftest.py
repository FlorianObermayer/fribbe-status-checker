"""Shared fixtures for router-level HTTP tests.

Creates a minimal FastAPI test app (starsessions + starlette-csrf + all tested routers)
with ``dependency_overrides`` cleared before and after each test so that
individual tests can inject mocks cleanly via ``app.dependency_overrides``.
"""

from collections.abc import Generator
from datetime import datetime
from unittest.mock import MagicMock
from urllib.parse import quote
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient
from starsessions import InMemoryStore, SessionAutoloadMiddleware, SessionMiddleware

from app.api.hybrid_auth import AuthRedirectError
from app.api.requests import AuthRedirectQuery
from app.config import cfg
from app.csrf import FormFieldCSRFMiddleware
from app.routers import api_keys, auth, internal, misc, notification_ui, notifications, pages, push, status, wardens

TEST_ADMIN_TOKEN = "test-admin-token-" + "A" * 32

_UTC = ZoneInfo("UTC")
_MOCK_NOW = datetime(2026, 4, 13, 12, 0, 0, tzinfo=_UTC)


def mock_internal_svc() -> MagicMock:
    """Create a MagicMock for InternalService with sensible defaults."""
    svc = MagicMock()
    svc.get_last_updated.return_value = _MOCK_NOW
    svc.get_last_error.return_value = None
    svc.get_wardens_on_site.return_value = []
    svc.get_active_devices_ct.return_value = 0
    svc.get_first_device_on_site.return_value = None
    svc.get_last_device_on_site.return_value = None
    svc.get_last_service_started.return_value = _MOCK_NOW
    return svc


@pytest.fixture
def test_app() -> FastAPI:
    """Minimal FastAPI instance with real routers but no polling side-effects."""
    test_app = FastAPI()
    session_store = InMemoryStore()
    test_app.add_middleware(
        FormFieldCSRFMiddleware,
        secret=cfg.SESSION_SECRET_KEY,
        sensitive_cookies={"session_cookie"},
        header_name="x-csrf-token",
        cookie_secure=False,
        cookie_samesite="lax",
    )
    test_app.add_middleware(SessionAutoloadMiddleware)
    test_app.add_middleware(
        SessionMiddleware,
        store=session_store,
        cookie_name="session_cookie",
        lifetime=cfg.SESSION_MAX_AGE_SECONDS,
        cookie_https_only=False,
        cookie_same_site="lax",
    )
    test_app.include_router(misc.router)
    test_app.include_router(auth.router)
    test_app.include_router(status.router)
    test_app.include_router(push.router)
    test_app.include_router(api_keys.router)
    test_app.include_router(internal.router)
    test_app.include_router(notifications.router)
    test_app.include_router(notification_ui.router)
    test_app.include_router(wardens.router)
    test_app.include_router(pages.router)

    async def _handle_auth_redirect(_request: Request, exc: AuthRedirectError) -> RedirectResponse:
        safe_next = AuthRedirectQuery.sanitize_url(exc.next_url) or "/"
        return RedirectResponse(url=f"/auth?next={quote(safe_next, safe='/:?=&')}", status_code=302)

    test_app.add_exception_handler(AuthRedirectError, _handle_auth_redirect)  # type: ignore[arg-type]

    return test_app


@pytest.fixture
def client(test_app: FastAPI) -> Generator[TestClient, None, None]:
    """TestClient with a clean dependency_overrides slate for each test."""
    test_app.dependency_overrides.clear()
    with TestClient(test_app, raise_server_exceptions=True) as c:
        yield c
    test_app.dependency_overrides.clear()
