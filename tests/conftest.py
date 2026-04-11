"""Shared fixtures for router-level HTTP tests.

Creates a minimal FastAPI test app (SessionMiddleware + all tested routers)
with ``dependency_overrides`` cleared before and after each test so that
individual tests can inject mocks cleanly via ``app.dependency_overrides``.
"""

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

import app.env as env
from app.routers import internal, notifications, push, status

# A fixed ≥48-character token used as the admin credential in router tests.
TEST_ADMIN_TOKEN = "test-admin-routertests-AABBCCDD0123456789abcdef"  # noqa: S105


@pytest.fixture(scope="session")
def test_app() -> FastAPI:
    """Minimal FastAPI instance with real routers but no polling side-effects."""
    app = FastAPI()
    app.add_middleware(
        SessionMiddleware,
        secret_key=env.SESSION_SECRET_KEY,
        session_cookie="test_session",
    )
    app.include_router(status.router)
    app.include_router(push.router)
    app.include_router(internal.router)
    app.include_router(notifications.router)
    return app


@pytest.fixture()
def client(test_app: FastAPI) -> Generator[TestClient, None, None]:
    """TestClient with a clean dependency_overrides slate for each test."""
    test_app.dependency_overrides.clear()
    with TestClient(test_app, raise_server_exceptions=True) as c:
        yield c
    test_app.dependency_overrides.clear()
