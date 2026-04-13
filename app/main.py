import asyncio
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Request, Response
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, RedirectResponse
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


_csp_domain_src: list[str] = [env.CSP_DOMAIN] if env.CSP_DOMAIN else []
_csp = (
    ContentSecurityPolicy()
    .default_src("'self'", *_csp_domain_src)
    .script_src(
        "'self'",
        *_csp_domain_src,
        "'sha256-nMQAQejeJNzygq389v6PkLiAKpJ1N8/ayX83QB0thSU='",  # Hash of the FOUC-prevention inline <script>
    )
    .style_src("'self'", *_csp_domain_src, "https://fonts.googleapis.com")
    .font_src("'self'", *_csp_domain_src, "https://fonts.gstatic.com")
    .object_src("'none'")
    .img_src("'self'", *_csp_domain_src, "https://img.shields.io", "data:")
    .custom_directive("style-src-attr", "'unsafe-inline'")
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
    docs_url=None,  # Replaced by a custom /docs route that auto-injects the CSRF header.
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


@app.get("/docs", include_in_schema=False)
async def swagger_ui() -> HTMLResponse:
    """Serve Swagger UI with automatic CSRF-token injection from the browser cookie.

    The starlette-csrf middleware sets the ``csrftoken`` cookie on the first GET
    response but never injects it as the ``X-CSRF-Token`` request header. Without
    this override every state-changing call made from Swagger UI would be rejected
    with 403 when the browser session cookie is present.

    /docs is already excluded from the app's Content-Security-Policy headers, so
    the inline script below is safe.
    """
    html = get_swagger_ui_html(openapi_url="/openapi.json", title="Fribbe Status Checker — Docs")
    # Patch window.fetch so that the csrftoken cookie is forwarded as the
    # X-CSRF-Token header on every request Swagger UI makes.
    raw = html.body
    body = raw.decode() if isinstance(raw, bytes) else bytes(raw).decode()
    csrf_inject = (
        "<script>"
        "(function(){"
        "var _f=window.fetch;"
        "window.fetch=function(u,o){"
        "o=o||{};"
        "var m=document.cookie.match(/(?:^|;\\s*)csrftoken=([^;]*)/);"
        "if(m){o.headers=Object.assign({},o.headers,{'X-CSRF-Token':decodeURIComponent(m[1])});}"
        "return _f.call(this,u,o);"
        "};"
        "})();"
        "</script>"
    )
    body = body.replace("</body>", csrf_inject + "\n</body>", 1)
    return HTMLResponse(content=body)


update_openapi_schema(app)
