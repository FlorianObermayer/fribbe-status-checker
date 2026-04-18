import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from starsessions import regenerate_session_id

from app.api.hybrid_auth import create_session
from app.api.requests import AuthBody
from app.config import cfg
from app.routers.nav_context import Route

_logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(Route.URL_AUTH, include_in_schema=False)
async def post_auth(
    request: Request,
    body: AuthBody,
) -> JSONResponse:
    """Authenticate with a token and create a session."""
    if not create_session(request, body.token):
        raise HTTPException(status_code=401, detail="Invalid token")
    regenerate_session_id(request)
    return JSONResponse({"redirect": body.next})


@router.post(Route.URL_SIGNOUT, include_in_schema=False)
async def signout(request: Request) -> RedirectResponse:
    """Clear the session and redirect to the home page."""
    # CSRF enforcement is handled by FormFieldCSRFMiddleware (header or hidden form field).
    _logger.info("Sign-out (client %s)", request.client and request.client.host)
    request.session.clear()
    response = RedirectResponse(url=Route.URL_INDEX, status_code=303)
    # Explicitly expire the CSRF token cookie; the CSRF middleware only sets it
    # when absent, so it would otherwise linger in the browser after sign-out.
    response.delete_cookie("csrftoken", path="/", samesite="lax", secure=cfg.HTTPS_ONLY)
    return response
