import html
import json
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starsessions import regenerate_session_id

import app.env as env
from app.api.EphemeralAPIKeyStore import EphemeralAPIKeyStore
from app.api.HybridAuth import PageAuth, create_session, resolve_session_subject
from app.api.Requests import NotificationQuery
from app.api.Schema import requires_auth_extra
from app.version import VERSION

router = APIRouter()


def _is_signed_in(request: Request) -> bool:
    session_subject = resolve_session_subject(request)
    if session_subject is not None:
        return True

    # Clear stale / legacy session entries.
    if (
        request.session.get("api_key")
        or request.session.get("admin_token_hash")
        or request.session.get("auth_session_id")
    ):
        request.session.clear()

    return False


def sanitize_next(next_url: str) -> str:
    if not next_url.startswith("/") or next_url.startswith("//"):
        return "/"
    return next_url


@router.get("/", response_class=HTMLResponse, tags=["HTML"])
async def get_html(request: Request, for_date: str = "today") -> HTMLResponse:  # keep unused variable for api reference
    signed_in = _is_signed_in(request)
    with Path("app/static/index.html").open() as f:
        content = f.read()
    bootstrap_mode = EphemeralAPIKeyStore.is_empty() and not env.ADMIN_TOKEN
    content = content.replace("__SIGNED_IN__", json.dumps(signed_in))
    content = content.replace("__SHOW_ADMIN_AUTH__", json.dumps(env.SHOW_ADMIN_AUTH))
    content = content.replace("__BOOTSTRAP_MODE__", json.dumps(bootstrap_mode))
    content = content.replace("__VERSION__", VERSION)
    return HTMLResponse(content)


@router.get("/auth", response_class=HTMLResponse, include_in_schema=False)
async def get_auth_page(request: Request, next: str = "/") -> HTMLResponse:
    next = sanitize_next(next)
    signed_in = _is_signed_in(request)
    with Path("app/static/auth.html").open() as f:
        content = f.read()
    safe_next = html.escape(next, quote=True)
    content = content.replace("__NEXT_DATA__", safe_next)
    content = content.replace("__SIGNED_IN__", json.dumps(signed_in))
    content = content.replace("__VERSION__", VERSION)
    return HTMLResponse(content)


@router.post("/auth", include_in_schema=False)
async def post_auth(request: Request, token: str = Body(...), next: str = Body("/")) -> JSONResponse:
    next = sanitize_next(next)
    if not create_session(request, token):
        raise HTTPException(status_code=401, detail="Invalid token")
    regenerate_session_id(request)
    return JSONResponse({"redirect": next})


@router.post("/signout", include_in_schema=False)
async def signout(request: Request) -> JSONResponse:
    # CSRF enforcement is handled by starlette-csrf middleware.
    request.session.clear()
    return JSONResponse({"redirect": "/"})


@router.get("/notification-create", response_class=HTMLResponse, tags=["Notifications", "HTML"])
async def get_notification_builder(request: Request, _: str = Depends(PageAuth())) -> HTMLResponse:
    with Path("app/static/notification-create.html").open() as f:
        content = f.read()
    content = content.replace("__VERSION__", VERSION)
    return HTMLResponse(content)


@router.get(
    "/preview/notifications",
    tags=["Notifications"],
    openapi_extra=requires_auth_extra(),
)
async def get_notification_preview(
    request: Request,
    _: NotificationQuery = Query(...),
    __: str = Depends(PageAuth()),
) -> HTMLResponse:  # keep unused variable for api reference
    with Path("app/static/index.html").open() as f:
        content = f.read()
    content = content.replace("__SIGNED_IN__", json.dumps(True))
    content = content.replace("__SHOW_ADMIN_AUTH__", json.dumps(env.SHOW_ADMIN_AUTH))
    content = content.replace("__BOOTSTRAP_MODE__", json.dumps(False))
    content = content.replace("__VERSION__", VERSION)
    return HTMLResponse(content)
