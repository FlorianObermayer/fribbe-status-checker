"""Shared fixtures for router-level HTTP tests.

Creates a minimal FastAPI test app (starsessions + starlette-csrf + all tested routers)
with ``dependency_overrides`` cleared before and after each test so that
individual tests can inject mocks cleanly via ``app.dependency_overrides``.
"""

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette_csrf.middleware import CSRFMiddleware
from starsessions import InMemoryStore, SessionAutoloadMiddleware, SessionMiddleware

from app import env
from app.routers import api_keys, internal, misc, notifications, pages, push, status, wardens

TEST_ADMIN_TOKEN = "test-admin-token-" + "A" * 32


@pytest.fixture
def test_app() -> FastAPI:
    """Minimal FastAPI instance with real routers but no polling side-effects."""
    test_app = FastAPI()
    session_store = InMemoryStore()
    test_app.add_middleware(
        CSRFMiddleware,
        secret=env.SESSION_SECRET_KEY,
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
        lifetime=env.SESSION_MAX_AGE_SECONDS,
        cookie_https_only=False,
        cookie_same_site="lax",
    )
    test_app.include_router(misc.router)
    test_app.include_router(status.router)
    test_app.include_router(push.router)
    test_app.include_router(api_keys.router)
    test_app.include_router(internal.router)
    test_app.include_router(notifications.router)
    test_app.include_router(wardens.router)
    test_app.include_router(pages.router)
    return test_app


@pytest.fixture
def client(test_app: FastAPI) -> Generator[TestClient, None, None]:
    """TestClient with a clean dependency_overrides slate for each test."""
    test_app.dependency_overrides.clear()
    with TestClient(test_app, raise_server_exceptions=True) as c:
        yield c
    test_app.dependency_overrides.clear()
