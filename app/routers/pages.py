from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starsessions import regenerate_session_id

from app import env
from app.api.access_role import AccessRole
from app.api.ephemeral_api_key_store import EphemeralAPIKeyStore
from app.api.hybrid_auth import PageAuth, create_session, resolve_session_subject
from app.api.requests import NotificationQuery
from app.api.schema import requires_auth_extra
from app.format import seconds_to_human
from app.version import VERSION

router = APIRouter()
_templates = Jinja2Templates(directory="app/templates")


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
    """Ensure the redirect URL is a safe relative path."""
    if not next_url.startswith("/") or next_url.startswith("//"):
        return "/"
    return next_url


@router.get("/", response_class=HTMLResponse, tags=["HTML"])
def get_html(request: Request, _for_date: str = "today") -> HTMLResponse:
    """Serve the main index page with injected runtime config."""
    signed_in = _is_signed_in(request)
    bootstrap_mode = EphemeralAPIKeyStore.is_empty() and not env.ADMIN_TOKEN
    return _templates.TemplateResponse(
        request,
        "index.html",
        context={
            "signed_in": signed_in,
            "show_admin_auth": env.SHOW_ADMIN_AUTH,
            "bootstrap_mode": bootstrap_mode,
            "app_url": env.APP_URL,
            "version": VERSION,
            "show_legal": bool(env.OPERATOR_NAME and env.OPERATOR_EMAIL),
        },
    )


@router.get("/legal", response_class=HTMLResponse, include_in_schema=False)
def get_legal_page(request: Request) -> HTMLResponse:
    """Serve the Impressum & Datenschutz page.

    Returns 404 when OPERATOR_NAME or OPERATOR_EMAIL are not configured.
    """
    if not env.OPERATOR_NAME or not env.OPERATOR_EMAIL:
        raise HTTPException(status_code=404, detail="Legal page not configured")
    return _templates.TemplateResponse(
        request,
        "legal.html",
        context={
            "version": VERSION,
            "operator_name": env.OPERATOR_NAME,
            "operator_email": env.OPERATOR_EMAIL,
            "session_max_age": seconds_to_human(env.SESSION_MAX_AGE_SECONDS),
        },
    )


@router.get("/auth", response_class=HTMLResponse, include_in_schema=False)
def get_auth_page(request: Request, next_url: Annotated[str, Query(alias="next")] = "/") -> HTMLResponse:
    """Serve the authentication page."""
    next_url = sanitize_next(next_url)
    signed_in = _is_signed_in(request)
    return _templates.TemplateResponse(
        request,
        "auth.html",
        context={
            "next_url": next_url,
            "signed_in": signed_in,
            "version": VERSION,
        },
    )


@router.post("/auth", include_in_schema=False)
async def post_auth(
    request: Request,
    token: Annotated[str, Body()],
    next_url: Annotated[str, Body(alias="next")] = "/",
) -> JSONResponse:
    """Authenticate with a token and create a session."""
    next_url = sanitize_next(next_url)
    if not create_session(request, token):
        raise HTTPException(status_code=401, detail="Invalid token")
    regenerate_session_id(request)
    return JSONResponse({"redirect": next_url})


@router.post("/signout", include_in_schema=False)
async def signout(request: Request) -> JSONResponse:
    """Clear the session and redirect to the home page."""
    # CSRF enforcement is handled by starlette-csrf middleware.
    request.session.clear()
    return JSONResponse({"redirect": "/"})


@router.get("/notification-create", response_class=HTMLResponse, tags=["Notifications", "HTML"])
def get_notification_builder(
    request: Request, _: Annotated[str, Depends(PageAuth(min_role=AccessRole.NOTIFICATION_OPERATOR))]
) -> HTMLResponse:
    """Serve the notification creation page."""
    return _templates.TemplateResponse(
        request,
        "notification-create.html",
        context={"version": VERSION},
    )


@router.get(
    "/preview/notifications",
    tags=["Notifications"],
    openapi_extra=requires_auth_extra(),
)
def get_notification_preview(
    request: Request,
    _query: Annotated[NotificationQuery, Query()],
    _auth: Annotated[str, Depends(PageAuth())],
) -> HTMLResponse:
    """Serve a notification preview page."""
    return _templates.TemplateResponse(
        request,
        "index.html",
        context={
            "signed_in": True,
            "show_admin_auth": env.SHOW_ADMIN_AUTH,
            "bootstrap_mode": False,
            "app_url": env.APP_URL,
            "version": VERSION,
            "show_legal": bool(env.OPERATOR_NAME and env.OPERATOR_EMAIL),
        },
    )
