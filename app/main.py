#!/usr/bin/env python3
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from secure import ContentSecurityPolicy, Secure
from starlette_csrf.middleware import CSRFMiddleware
from starsessions import SessionAutoloadMiddleware, SessionMiddleware

import app.env as env
from app.api.HybridAuth import AuthRedirectException
from app.api.Schema import update_openapi_schema
from app.dependencies import shutdown, startup
from app.routers import api_keys, internal, misc, notifications, pages, push, status, wardens
from app.routers.pages import sanitize_next
from app.stores.FileSessionStore import FileSessionStore
from app.version import VERSION

_csp = (
    ContentSecurityPolicy()
    .default_src("'self'", "https://*.fribbe-beach.de")
    .script_src("'self'", "https://*.fribbe-beach.de")
    .style_src(
        "'self'",
        "https://*.fribbe-beach.de",
        "https://fonts.googleapis.com",
    )
    .font_src("'self'", "https://*.fribbe-beach.de", "https://fonts.gstatic.com")
    .object_src("'none'")
    .img_src("'self'", "https://*.fribbe-beach.de", "https://img.shields.io", "data:")
)
secure_headers = Secure(csp=_csp)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    startup()
    yield
    shutdown()


app = FastAPI(
    title="Fribbe Status Checker",
    version=VERSION,
    lifespan=lifespan,
    license_info={
        "name": "MIT",
        "url": "https://github.com/FlorianObermayer/fribbe-status-checker/blob/main/LICENSE",
    },
)

app.add_middleware(
    CSRFMiddleware,
    secret=env.SESSION_SECRET_KEY,
    sensitive_cookies={"session_cookie"},
    header_name="x-csrf-token",
    cookie_secure=env.HTTPS_ONLY,
    cookie_samesite="lax",
)

app.add_middleware(SessionAutoloadMiddleware)

_session_store = FileSessionStore(str(Path(env.LOCAL_DATA_PATH) / "sessions"))

app.add_middleware(
    SessionMiddleware,
    store=_session_store,
    cookie_name="session_cookie",
    lifetime=env.SESSION_MAX_AGE_SECONDS,
    cookie_https_only=env.HTTPS_ONLY,
    cookie_same_site="lax",
    rolling=True,
)


@app.exception_handler(AuthRedirectException)
async def auth_redirect_handler(request: Request, exc: AuthRedirectException) -> RedirectResponse:
    safe_next = sanitize_next(exc.next_url)
    return RedirectResponse(url=f"/auth?next={quote(safe_next, safe='/:?=&')}", status_code=302)


@app.middleware("http")
async def add_security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    response = await call_next(request)
    if request.url.path not in ("/docs", "/redoc", "/openapi.json"):
        await secure_headers.set_headers_async(response)  # type: ignore
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    logger = logging.getLogger("uvicorn.error")
    api_key = request.headers.get("api_key")
    if api_key:
        logger.info(f"-H api_key[:2]={api_key[:2]}")
    response = await call_next(request)
    return response


app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(misc.router)
app.include_router(push.router)
app.include_router(status.router)
app.include_router(api_keys.router)
app.include_router(internal.router)
app.include_router(notifications.router)
app.include_router(wardens.router)
app.include_router(pages.router)

update_openapi_schema(app)
