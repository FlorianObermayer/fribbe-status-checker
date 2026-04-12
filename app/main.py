import asyncio
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from secure import ContentSecurityPolicy, Secure
from starlette_csrf.middleware import CSRFMiddleware
from starsessions import SessionAutoloadMiddleware, SessionMiddleware

from app import env
from app.api.hybrid_auth import AuthRedirectError
from app.api.redact import redact_key
from app.api.schema import update_openapi_schema
from app.dependencies import shutdown, startup
from app.routers import api_keys, internal, misc, notifications, pages, push, status, wardens
from app.routers.pages import sanitize_next
from app.stores.file_session_store import FileSessionStore
from app.version import VERSION

_logger = logging.getLogger("uvicorn.error")


_csp = (
    ContentSecurityPolicy()
    .default_src("'self'", "https://*.fribbe-beach.de")
    .script_src(
        "'self'",
        "https://*.fribbe-beach.de",
        "'sha256-nMQAQejeJNzygq389v6PkLiAKpJ1N8/ayX83QB0thSU='",  # Hash of the FOUC-prevention inline <script>
    )
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
    """Start and stop services around the application lifetime."""
    startup()
    cleanup_task = asyncio.create_task(_session_cleanup_loop())
    yield
    cleanup_task.cancel()
    with suppress(asyncio.CancelledError):
        await cleanup_task
    shutdown()


async def _session_cleanup_loop() -> None:
    """Periodically remove expired session files."""
    while True:
        await asyncio.sleep(env.SESSION_CLEANUP_INTERVAL_SECONDS)
        try:
            await _session_store.cleanup(env.SESSION_MAX_AGE_SECONDS)
        except Exception:
            _logger.exception("Session cleanup failed")


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


@app.exception_handler(AuthRedirectError)
async def auth_redirect_handler(_request: Request, exc: AuthRedirectError) -> RedirectResponse:
    """Redirect unauthenticated page requests to /auth."""
    safe_next = sanitize_next(exc.next_url)
    return RedirectResponse(url=f"/auth?next={quote(safe_next, safe='/:?=&')}", status_code=302)


@app.middleware("http")
async def add_security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Attach security headers to non-documentation responses."""
    response = await call_next(request)
    if request.url.path not in ("/docs", "/redoc", "/openapi.json"):
        for name, value in secure_headers.headers.items():
            response.headers[name] = value
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Log incoming requests that carry an API key header."""
    logger = logging.getLogger("uvicorn.error")
    api_key = request.headers.get("api_key")
    logger.info("-H api_key=%s", redact_key(api_key))
    return await call_next(request)


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
